# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class PurchaseApprovalMatrixDiagram(models.TransientModel):
    _name = 'purchase.approval.matrix.diagram'
    _description = 'Approval Workflow Diagram'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    rule_count = fields.Integer(compute='_compute_diagram', store=False)
    level_count = fields.Integer(compute='_compute_diagram', store=False)
    diagram_html = fields.Html(
        string='Diagram',
        compute='_compute_diagram',
        sanitize=False,
        store=False,
    )

    # (main_color, light_bg) pairs, one per level (cycles if > 10 levels)
    _COLORS = [
        ('#4472C4', '#EBF0FA'),
        ('#198754', '#D1E7DD'),
        ('#ED7D31', '#FDF2EB'),
        ('#875A7B', '#F2EBF0'),
        ('#DC3545', '#F8D7DA'),
        ('#0B85A0', '#D0EEF5'),
        ('#6F42C1', '#E8D5F9'),
        ('#20C997', '#D2F4EA'),
        ('#D4860A', '#FFF3CD'),
        ('#495057', '#F8F9FA'),
    ]

    @api.depends('company_id')
    def _compute_diagram(self):
        for rec in self:
            rules = self.env['purchase.approval.matrix'].search(
                [('company_id', '=', rec.company_id.id), ('active', '=', True)],
                order='approval_level asc, sequence asc, id asc',
            )

            levels = {}
            for rule in rules:
                levels.setdefault(rule.approval_level, []).append(rule)

            rec.rule_count = len(rules)
            rec.level_count = len(levels)

            if not rules:
                rec.diagram_html = rec._empty_html()
            else:
                rec.diagram_html = rec._build_html(levels)

    # ------------------------------------------------------------------
    # HTML builders
    # ------------------------------------------------------------------

    def _empty_html(self):
        return (
            '<div style="text-align:center;padding:48px 24px;'
            'color:#6c757d;font-family:system-ui,sans-serif;">'
            '<div style="font-size:52px;margin-bottom:16px;">&#9881;</div>'
            '<h4 style="margin:0 0 8px 0;color:#333;">No Approval Rules Configured</h4>'
            '<p style="margin:0;font-size:13px;">Click <b>+ New Rule</b> below to add your first approval rule.</p>'
            '</div>'
        )

    def _build_html(self, levels):
        parts = []
        n_levels = len(levels)
        n_rules = sum(len(r) for r in levels.values())
        parts.append(
            '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',Roboto,sans-serif;">'
        )

        # ── Stats banner ──────────────────────────────────────────────
        parts.append(f'''
<div style="display:flex;align-items:center;gap:0;margin-bottom:20px;
            border-radius:10px;overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,.12);">
  <div style="background:#875A7B;color:white;padding:18px 28px;text-align:center;min-width:110px;">
    <div style="font-size:32px;font-weight:700;line-height:1;">{n_levels}</div>
    <div style="font-size:11px;opacity:.85;margin-top:2px;">Level{"s" if n_levels != 1 else ""}</div>
  </div>
  <div style="background:#6B4460;color:white;padding:18px 28px;text-align:center;min-width:110px;">
    <div style="font-size:32px;font-weight:700;line-height:1;">{n_rules}</div>
    <div style="font-size:11px;opacity:.85;margin-top:2px;">Rule{"s" if n_rules != 1 else ""}</div>
  </div>
  <div style="flex:1;background:#F8F4F7;padding:14px 20px;">
    <div style="font-size:12px;color:#555;line-height:1.6;">
      A purchase order must pass <b>all {n_levels} level{"s" if n_levels != 1 else ""}</b>
      in sequence before it can be confirmed.
      Rules within the same level are matched by <b>amount, department, and category</b>.
    </div>
  </div>
</div>''')

        # ── Flow diagram ───────────────────────────────────────────────
        parts.append(
            '<div style="display:flex;align-items:flex-start;overflow-x:auto;'
            'padding:28px 20px;background:#f8f9fa;border-radius:10px;'
            'border:1px solid #dee2e6;">'
        )

        # Start node
        parts.append('''
<div style="display:flex;flex-direction:column;align-items:center;
            min-width:88px;margin-top:16px;flex-shrink:0;">
  <div style="background:#6c757d;color:white;padding:14px 12px;border-radius:10px;
              text-align:center;font-size:11px;font-weight:600;
              box-shadow:0 3px 8px rgba(0,0,0,.18);min-width:80px;
              border-bottom:3px solid #495057;">
    <div style="font-size:22px;margin-bottom:4px;">&#128203;</div>
    PO Draft
  </div>
</div>''')

        for level, level_rules in sorted(levels.items()):
            main, light = self._COLORS[(level - 1) % len(self._COLORS)]

            # Arrow
            parts.append(f'''
<div style="display:flex;align-items:center;margin-top:26px;flex-shrink:0;padding:0 4px;">
  <div style="width:28px;height:2px;background:{main};"></div>
  <div style="width:0;height:0;border-top:7px solid transparent;
              border-bottom:7px solid transparent;border-left:11px solid {main};"></div>
</div>''')

            # Level column
            parts.append(f'''
<div style="display:flex;flex-direction:column;min-width:200px;max-width:240px;flex-shrink:0;">
  <div style="background:{main};color:white;padding:7px 14px;
              border-radius:10px 10px 0 0;text-align:center;
              font-weight:700;font-size:12px;letter-spacing:.8px;">
    LEVEL {level}
  </div>
  <div style="border:2px solid {main};border-top:none;border-radius:0 0 10px 10px;
              padding:8px;background:white;display:flex;flex-direction:column;
              gap:6px;min-height:80px;">''')

            for rule in level_rules:
                # Approver line
                if rule.approver_user_id:
                    approver = f'&#128100; {rule.approver_user_id.name}'
                elif rule.approver_group_id:
                    approver = f'&#128101; {rule.approver_group_id.name}'
                else:
                    approver = '&#9888; No approver set'

                # Amount range
                sym = rule.currency_id.symbol or rule.currency_id.name or ''
                if rule.min_amount and rule.max_amount:
                    amount = (
                        f'&#128176; {sym}{rule.min_amount:,.0f}'
                        f' &#8211; {sym}{rule.max_amount:,.0f}'
                    )
                elif rule.min_amount:
                    amount = f'&#128176; Above {sym}{rule.min_amount:,.0f}'
                elif rule.max_amount:
                    amount = f'&#128176; Up to {sym}{rule.max_amount:,.0f}'
                else:
                    amount = '&#128176; Any amount'

                # Optional filter badges
                badges = ''
                if rule.department_id:
                    badges += (
                        f'<span style="background:#e9ecef;color:#495057;'
                        f'padding:2px 7px;border-radius:10px;font-size:10px;">'
                        f'&#127970; {rule.department_id.name}</span>'
                    )
                if rule.product_category_id:
                    badges += (
                        f'<span style="background:#e9ecef;color:#495057;'
                        f'padding:2px 7px;border-radius:10px;font-size:10px;">'
                        f'&#127991; {rule.product_category_id.name}</span>'
                    )
                if badges:
                    badges = (
                        f'<div style="margin-top:5px;display:flex;flex-wrap:wrap;gap:3px;">'
                        f'{badges}</div>'
                    )

                parts.append(f'''
    <div style="background:{light};border:1px solid {main}40;
                border-radius:7px;padding:8px 10px;">
      <div style="font-weight:600;font-size:11px;color:#222;margin-bottom:5px;
                  padding-bottom:4px;border-bottom:1px solid {main}25;">
        {rule.name}
      </div>
      <div style="font-size:10px;color:#444;line-height:1.8;">
        <div>{approver}</div>
        <div>{amount}</div>
      </div>
      {badges}
    </div>''')

            parts.append('  </div>\n</div>')  # close level column

        # Final arrow + Approved node
        parts.append('''
<div style="display:flex;align-items:center;margin-top:26px;flex-shrink:0;padding:0 4px;">
  <div style="width:28px;height:2px;background:#198754;"></div>
  <div style="width:0;height:0;border-top:7px solid transparent;
              border-bottom:7px solid transparent;border-left:11px solid #198754;"></div>
</div>
<div style="display:flex;flex-direction:column;align-items:center;
            min-width:88px;margin-top:16px;flex-shrink:0;">
  <div style="background:#198754;color:white;padding:14px 12px;border-radius:10px;
              text-align:center;font-size:11px;font-weight:600;
              box-shadow:0 3px 8px rgba(0,0,0,.18);min-width:80px;
              border-bottom:3px solid #146c43;">
    <div style="font-size:22px;margin-bottom:4px;">&#9989;</div>
    Approved
  </div>
</div>''')

        parts.append('</div>')  # close flow diagram

        # ── Rejection note ─────────────────────────────────────────────
        parts.append('''
<div style="margin-top:14px;padding:11px 16px;background:#FFF3CD;
            border:1px solid #FFC107;border-left:4px solid #FFC107;
            border-radius:6px;font-size:12px;color:#664D03;">
  <b>&#8617; Rejection path:</b> Any approver at any level can reject the PO.
  The buyer receives a notification with the reason and can either
  resubmit as-is or click <i>Reset for Editing</i> to amend the order first.
</div>''')

        parts.append('</div>')  # close outer wrapper
        return ''.join(parts)

    # ------------------------------------------------------------------
    # Wizard actions (footer buttons)
    # ------------------------------------------------------------------

    def action_new_rule(self):
        self.ensure_one()
        return {
            'name': _('New Approval Rule'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.approval.matrix',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_company_id': self.company_id.id},
        }

    def action_open_matrix(self):
        self.ensure_one()
        return {
            'name': _('Approval Matrix'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.approval.matrix',
            'view_mode': 'list,kanban,form',
            'target': 'current',
            'context': {
                'search_default_active': 1,
                'default_company_id': self.company_id.id,
            },
        }
