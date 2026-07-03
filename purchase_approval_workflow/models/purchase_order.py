# -*- coding: utf-8 -*-
import secrets
from datetime import timedelta
from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # ------------------------------------------------------------------
    # Approval workflow state
    # ------------------------------------------------------------------

    approval_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting_approval', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval State',
        default='draft',
        tracking=True,
        copy=False,
        index=True,
        readonly=True,
    )

    display_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('sent', 'RFQ Sent'),
            ('waiting_approval', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('purchase', 'Purchase Order'),
            ('done', 'Locked'),
            ('cancel', 'Cancelled'),
        ],
        string='Status',
        compute='_compute_display_state',
        store=True,
    )

    # ------------------------------------------------------------------
    # Who did what and when
    # ------------------------------------------------------------------

    submitted_by = fields.Many2one(
        'res.users',
        string='Submitted By',
        copy=False,
        tracking=True,
        readonly=True,
    )
    submitted_date = fields.Datetime(
        string='Submission Date',
        copy=False,
        tracking=True,
        readonly=True,
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Last Approved By',
        copy=False,
        tracking=True,
        readonly=True,
    )
    approved_date = fields.Datetime(
        string='Last Approval Date',
        copy=False,
        tracking=True,
        readonly=True,
    )
    rejected_by = fields.Many2one(
        'res.users',
        string='Rejected By',
        copy=False,
        tracking=True,
        readonly=True,
    )
    rejected_date = fields.Datetime(
        string='Rejection Date',
        copy=False,
        tracking=True,
        readonly=True,
    )

    approval_notes = fields.Text(string='Approval Notes', copy=False)

    # ------------------------------------------------------------------
    # Current approver tracking
    # ------------------------------------------------------------------

    current_approver_id = fields.Many2one(
        'res.users',
        string='Current Approver',
        copy=False,
        tracking=True,
        readonly=True,
    )
    current_approval_level = fields.Integer(
        string='Current Approval Level',
        default=0,
        copy=False,
        readonly=True,
    )
    current_approval_matrix_id = fields.Many2one(
        'purchase.approval.matrix',
        string='Current Approval Rule',
        copy=False,
        readonly=True,
        ondelete='set null',
    )

    # ------------------------------------------------------------------
    # Approval history
    # ------------------------------------------------------------------

    approval_history_ids = fields.One2many(
        'purchase.approval.history',
        'purchase_order_id',
        string='Approval History',
        copy=False,
    )
    approval_history_count = fields.Integer(
        compute='_compute_approval_history_count',
        string='Approvals',
    )

    # ------------------------------------------------------------------
    # UI computed fields
    # ------------------------------------------------------------------

    can_approve = fields.Boolean(
        compute='_compute_can_approve',
        string='Can Approve',
    )
    approval_workflow_enabled = fields.Boolean(
        compute='_compute_approval_workflow_enabled',
        string='Workflow Enabled',
    )

    # ------------------------------------------------------------------
    # Budget Check (Feature 8)
    # ------------------------------------------------------------------

    budget_remaining = fields.Monetary(
        compute='_compute_budget_remaining',
        string='Remaining Budget',
        currency_field='currency_id',
        store=False,
        help='Remaining budget for the analytic account / cost center linked to this order.',
    )
    budget_exceeded = fields.Boolean(
        compute='_compute_budget_remaining',
        string='Budget Exceeded',
        store=False,
    )

    @api.depends('amount_total', 'current_approval_matrix_id')
    def _compute_budget_remaining(self):
        for order in self:
            order.budget_remaining = 0.0
            order.budget_exceeded = False
            matrix = order.current_approval_matrix_id
            if not matrix or not matrix.max_amount:
                continue
            # Show how much headroom remains under the current level's upper threshold
            order.budget_remaining = matrix.max_amount - order.amount_total
            order.budget_exceeded = order.amount_total > matrix.max_amount

    def _is_budget_check_enabled(self):
        return (
            self._get_param('purchase_approval_workflow.enable_budget_check', 'False') == 'True'
        )

    # ------------------------------------------------------------------
    # Urgency Override (Feature 13)
    # ------------------------------------------------------------------

    approval_urgency = fields.Selection(
        selection=[
            ('normal', 'Normal'),
            ('urgent', 'Urgent'),
            ('critical', 'Critical — Skip Levels'),
        ],
        string='Urgency',
        default='normal',
        copy=False,
        tracking=True,
        help='Set to Urgent to flag this order for immediate attention. '
             '"Critical — Skip Levels" routes the order directly to the highest '
             'configured approval level, bypassing intermediate levels.',
    )

    # ------------------------------------------------------------------
    # Change Summary on Resubmission (Feature 10)
    # ------------------------------------------------------------------

    last_submission_snapshot = fields.Text(
        string='Last Submission Snapshot',
        copy=False,
        readonly=True,
        groups='base.group_system',
        help='JSON snapshot of key PO fields taken at last submission for change detection.',
    )

    def _build_snapshot(self):
        """Return a dict of key PO fields for change comparison."""
        self.ensure_one()
        return {
            'amount_total': self.amount_total,
            'partner_id': self.partner_id.id,
            'partner_name': self.partner_id.name,
            'date_order': fields.Datetime.to_string(self.date_order) if self.date_order else '',
            'lines': [
                {
                    'product': line.product_id.name,
                    'qty': line.product_qty,
                    'price': line.price_unit,
                }
                for line in self.order_line
            ],
        }

    def _post_change_summary(self, old_snapshot_json):
        """Compare old snapshot with current state and post a chatter message."""
        import json
        self.ensure_one()
        if not old_snapshot_json:
            return
        try:
            old = json.loads(old_snapshot_json)
        except (ValueError, TypeError):
            return

        current = self._build_snapshot()
        changes = []

        if old.get('partner_name') != current.get('partner_name'):
            changes.append(
                Markup('Vendor changed from <b>%s</b> to <b>%s</b>.')
                % (escape(old.get('partner_name', '—')), escape(current.get('partner_name', '—')))
            )
        if old.get('amount_total') != current.get('amount_total'):
            changes.append(
                Markup('Total amount changed from <b>%s</b> to <b>%s</b>.')
                % (
                    '{:,.2f}'.format(old.get('amount_total', 0)),
                    '{:,.2f}'.format(current.get('amount_total', 0)),
                )
            )
        if old.get('date_order') != current.get('date_order'):
            changes.append(
                Markup('Order date changed from <b>%s</b> to <b>%s</b>.')
                % (escape(old.get('date_order', '—')), escape(current.get('date_order', '—')))
            )
        old_lines = len(old.get('lines', []))
        new_lines = len(current.get('lines', []))
        if old_lines != new_lines:
            changes.append(
                Markup('Number of order lines changed from <b>%d</b> to <b>%d</b>.')
                % (old_lines, new_lines)
            )

        if changes:
            items = Markup('').join(Markup('<li>%s</li>') % c for c in changes)
            self.message_post(
                body=Markup('<b>Changes since last rejection:</b><ul>%s</ul>') % items,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    # ------------------------------------------------------------------
    # Email one-click token (Feature 2)
    # ------------------------------------------------------------------

    approval_token = fields.Char(
        string='Approval Token',
        copy=False,
        readonly=True,
        index=True,
        groups='base.group_system',
    )

    # ------------------------------------------------------------------
    # SLA fields
    # ------------------------------------------------------------------

    approval_deadline = fields.Datetime(
        string='Approval Deadline',
        copy=False,
        readonly=True,
        tracking=True,
        help='Deadline by which the current approval level must be completed. '
             'Set automatically from the Approval Matrix SLA configuration.',
    )
    is_overdue = fields.Boolean(
        compute='_compute_is_overdue',
        string='Approval Overdue',
        store=False,
    )

    # ------------------------------------------------------------------
    # Computed field implementations
    # ------------------------------------------------------------------

    @api.depends('state', 'approval_state')
    def _compute_display_state(self):
        for order in self:
            if order.state in ('purchase', 'done', 'cancel'):
                # Confirmed / closed states always win
                order.display_state = order.state
            elif order.approval_state == 'waiting_approval':
                # Approval state takes priority over RFQ Sent
                order.display_state = 'waiting_approval'
            elif order.approval_state == 'approved':
                order.display_state = 'approved'
            elif order.approval_state == 'rejected':
                order.display_state = 'rejected'
            elif order.state == 'sent':
                order.display_state = 'sent'
            else:
                order.display_state = 'draft'

    @api.depends('approval_history_ids')
    def _compute_approval_history_count(self):
        for order in self:
            order.approval_history_count = len(order.approval_history_ids)

    @api.depends('approval_state', 'current_approver_id', 'current_approval_matrix_id')
    @api.depends_context('uid')
    def _compute_can_approve(self):
        user = self.env.user
        is_admin = user.has_group(
            'purchase_approval_workflow.group_purchase_approval_administrator'
        )
        manager_override = (
            self._get_param('purchase_approval_workflow.allow_manager_override', 'False') == 'True'
        )
        is_manager = user.has_group(
            'purchase_approval_workflow.group_purchase_approval_manager'
        )

        for order in self:
            if order.approval_state != 'waiting_approval':
                order.can_approve = False
                continue
            if is_admin:
                order.can_approve = True
                continue
            if manager_override and is_manager:
                order.can_approve = True
                continue
            # Specific user match (including delegation: if current approver delegated to user)
            approver = order.current_approver_id
            if approver and approver == user:
                order.can_approve = True
                continue
            # Delegation: user is the delegate of the current approver
            if (approver and approver.approval_delegate_id == user
                    and approver.is_on_approval_leave):
                order.can_approve = True
                continue
            # Group-based match
            matrix = order.current_approval_matrix_id
            if matrix and matrix.approver_group_id:
                if user in matrix.approver_group_id.users:
                    order.can_approve = True
                    continue
            order.can_approve = False

    def _compute_approval_workflow_enabled(self):
        enabled = (
            self._get_param('purchase_approval_workflow.enabled', 'True') == 'True'
        )
        for order in self:
            order.approval_workflow_enabled = enabled

    @api.depends('approval_deadline', 'approval_state')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for order in self:
            order.is_overdue = (
                order.approval_state == 'waiting_approval'
                and bool(order.approval_deadline)
                and order.approval_deadline < now
            )

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _get_param(self, key, default='False'):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    def _is_workflow_enabled(self):
        return self._get_param('purchase_approval_workflow.enabled', 'True') == 'True'

    def _is_multi_level_enabled(self):
        return self._get_param('purchase_approval_workflow.enable_multi_level', 'True') == 'True'

    def _is_email_enabled(self):
        return (
            self._get_param('purchase_approval_workflow.enable_email_notifications', 'True') == 'True'
        )

    def _is_activity_enabled(self):
        return (
            self._get_param('purchase_approval_workflow.enable_mail_activities', 'True') == 'True'
        )

    def _is_sla_enabled(self):
        return self._get_param('purchase_approval_workflow.enable_sla', 'False') == 'True'

    def _get_buyer_hr_manager(self):
        """Return the HR manager of the buyer (user_id) based on HR employee record."""
        self.ensure_one()
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.user_id.id), ('company_id', '=', self.company_id.id)],
            limit=1,
        )
        if employee and employee.parent_id and employee.parent_id.user_id:
            return employee.parent_id.user_id
        return self.env['res.users']

    def _get_highest_approval_level(self):
        """Return the highest configured approval level for this company."""
        self.ensure_one()
        result = self.env['purchase.approval.matrix'].search(
            [('company_id', '=', self.company_id.id), ('active', '=', True)],
            order='approval_level desc',
            limit=1,
        )
        return result.approval_level if result else 1

    def _is_trusted_vendor_bypass_enabled(self):
        return (
            self._get_param('purchase_approval_workflow.enable_trusted_vendor_bypass', 'False') == 'True'
        )

    def _check_trusted_vendor_bypass(self):
        """Return True (and auto-approve) if this PO qualifies for trusted-vendor bypass."""
        self.ensure_one()
        vendor = self.partner_id
        if not vendor.approval_bypass:
            return False

        # Check amount limit (0 = no limit)
        if vendor.approval_bypass_limit:
            amount = self.amount_total
            if self.currency_id != self.company_id.currency_id:
                amount = self.currency_id._convert(
                    amount,
                    self.company_id.currency_id,
                    self.company_id,
                    self.date_order or fields.Date.today(),
                )
            if amount > vendor.approval_bypass_limit:
                return False

        # Auto-approve
        self.with_context(approval_workflow_action=True).write({
            'approval_state': 'approved',
            'submitted_by': self.env.uid,
            'submitted_date': fields.Datetime.now(),
            'approved_by': self.env.uid,
            'approved_date': fields.Datetime.now(),
        })
        self.message_post(
            body=Markup(
                '<b>Auto-Approved:</b> Vendor <b>%s</b> is marked as a trusted vendor. '
                'This purchase order has been automatically approved.'
            ) % escape(vendor.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return True

    # ------------------------------------------------------------------
    # Approval matrix lookup
    # ------------------------------------------------------------------

    def _get_approval_matrix(self, level):
        """Return the first matching purchase.approval.matrix rule for this order at the given level."""
        self.ensure_one()

        # Convert PO total to company currency for amount comparison
        amount = self.amount_total
        if self.currency_id != self.company_id.currency_id:
            amount = self.currency_id._convert(
                amount,
                self.company_id.currency_id,
                self.company_id,
                self.date_order or fields.Date.today(),
            )

        domain = [
            ('company_id', '=', self.company_id.id),
            ('approval_level', '=', level),
            ('active', '=', True),
        ]
        matrices = self.env['purchase.approval.matrix'].search(
            domain, order='sequence asc, id asc'
        )

        for matrix in matrices:
            if not self._matrix_matches_amount(matrix, amount):
                continue
            # Vendor-specific rule: skip if the matrix has a vendor filter that doesn't match
            if matrix.vendor_id and matrix.vendor_id != self.partner_id:
                continue
            if matrix.department_id and not self._matrix_matches_department(matrix):
                continue
            if matrix.product_category_id and not self._matrix_matches_category(matrix):
                continue
            return matrix

        return self.env['purchase.approval.matrix']

    def _matrix_matches_amount(self, matrix, company_amount):
        min_amt = matrix.min_amount or 0.0
        max_amt = matrix.max_amount  # 0 means no upper limit
        if company_amount < min_amt:
            return False
        if max_amt and company_amount > max_amt:
            return False
        return True

    def _get_no_matrix_error_message(self, level):
        """Explain specifically why no approval matrix matched."""
        self.ensure_one()

        amount = self.amount_total
        if self.currency_id != self.company_id.currency_id:
            amount = self.currency_id._convert(
                amount,
                self.company_id.currency_id,
                self.company_id,
                self.date_order or fields.Date.today(),
            )
        currency = self.company_id.currency_id.symbol or self.company_id.currency_id.name

        all_rules = self.env['purchase.approval.matrix'].search([
            ('company_id', '=', self.company_id.id),
            ('approval_level', '=', level),
            ('active', '=', True),
        ])

        if not all_rules:
            return _(
                'No active approval rule is configured for Level %(level)d.\n\n'
                'Please go to Purchase → Configuration → Approval Matrix and '
                'create a rule for this approval level.',
                level=level,
            )

        amount_exceeded = all(
            r.max_amount and amount > r.max_amount
            for r in all_rules
        )
        if amount_exceeded:
            max_configured = max(r.max_amount for r in all_rules if r.max_amount)
            return _(
                'The total of "%(po)s" (%(amount).2f %(currency)s) exceeds the '
                'maximum threshold configured for Level %(level)d '
                '(%(max).2f %(currency)s).\n\n'
                'To allow orders of this size, either:\n'
                '  • Increase the maximum amount on the Level %(level)d rule, or\n'
                '  • Add a new approval rule that covers amounts above %(max).2f %(currency)s.',
                po=self.name,
                amount=amount,
                max=max_configured,
                currency=currency,
                level=level,
            )

        return _(
            'No approval rule matches this purchase order for Level %(level)d.\n\n'
            'Possible causes:\n'
            '  • A vendor filter on the rule does not match "%(vendor)s"\n'
            '  • A department or product-category filter does not match\n\n'
            'Please review Purchase → Configuration → Approval Matrix.',
            level=level,
            vendor=self.partner_id.name or _('this vendor'),
        )

    def _matrix_matches_department(self, matrix):
        """Match PO user's department against the matrix department."""
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.user_id.id), ('company_id', '=', self.company_id.id)],
            limit=1,
        )
        return employee.department_id == matrix.department_id

    def _matrix_matches_category(self, matrix):
        """Match if any order line's product category is within the matrix category tree."""
        line_categories = self.order_line.mapped('product_id.categ_id')
        # Walk the category hierarchy upward to support parent matching
        all_categories = self.env['product.category']
        for cat in line_categories:
            current = cat
            while current:
                all_categories |= current
                current = current.parent_id
        return matrix.product_category_id in all_categories

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    def action_submit_for_approval(self):
        self.ensure_one()

        if not self._is_workflow_enabled():
            return self.button_confirm()

        # Auto-bypass for trusted vendors
        if self._is_trusted_vendor_bypass_enabled() and self._check_trusted_vendor_bypass():
            return True

        if self.state not in ('draft', 'sent'):
            raise UserError(_(
                'Only draft or sent RFQs can be submitted for approval.'
            ))
        if self.approval_state not in ('draft', 'rejected'):
            raise UserError(_(
                'This purchase order has already been submitted for approval.'
            ))
        if not self.order_line:
            raise UserError(_(
                'You cannot submit an empty purchase order for approval. '
                'Please add at least one product line.'
            ))

        # For Critical urgency: route directly to the highest configured approval level
        start_level = 1
        if self.approval_urgency == 'critical':
            start_level = self._get_highest_approval_level()

        matrix = self._get_approval_matrix(level=start_level)
        if not matrix:
            raise ValidationError(self._get_no_matrix_error_message(start_level))

        # Post change summary if this is a resubmission after rejection
        if self.approval_state == 'rejected' and self.last_submission_snapshot:
            self._post_change_summary(self.last_submission_snapshot)

        # Resolve approver: use HR manager if configured, else use the matrix user
        if matrix.use_hr_manager:
            approver_user = self._get_buyer_hr_manager()
        else:
            approver_user = matrix.approver_user_id
        # Resolve delegation: if approver is out of office, route to their delegate
        if approver_user:
            approver_user = approver_user._get_effective_approver()
        deadline = False
        if self._is_sla_enabled() and matrix.sla_days > 0:
            deadline = fields.Datetime.now() + timedelta(days=matrix.sla_days)
        import json
        self.with_context(approval_workflow_action=True).write({
            'approval_state': 'waiting_approval',
            'submitted_by': self.env.uid,
            'submitted_date': fields.Datetime.now(),
            'current_approver_id': approver_user.id if approver_user else False,
            'current_approval_level': start_level,
            'current_approval_matrix_id': matrix.id,
            'approval_deadline': deadline,
            'approval_token': secrets.token_urlsafe(32),
            'last_submission_snapshot': json.dumps(self._build_snapshot()),
        })

        submitter_name = self.env.user.name
        urgency_note = Markup('')
        if self.approval_urgency == 'urgent':
            urgency_note = Markup(' <span style="color:#e65100;font-weight:bold;">⚡ URGENT</span>')
        elif self.approval_urgency == 'critical':
            urgency_note = Markup(
                ' <span style="color:#c62828;font-weight:bold;">🚨 CRITICAL — Routed to Level %d</span>'
            ) % start_level
        self.message_post(
            body=Markup('<b>%s</b> submitted this RFQ for approval (Level %d — %s).%s')
                % (escape(submitter_name), start_level, escape(matrix.name), urgency_note),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        if self._is_activity_enabled():
            self._create_approval_activity(matrix)

        if self._is_email_enabled():
            self._send_submission_email()

        return True

    def action_approve(self):
        self.ensure_one()

        if not self.can_approve:
            raise UserError(_(
                'You are not authorised to approve this purchase order. '
                'Only the designated approver can take this action.'
            ))

        # Handle AND-logic parallel approval: record the vote first
        matrix = self.current_approval_matrix_id
        if (matrix and matrix.approval_type == 'all'
                and matrix.approver_group_id):
            return self._action_approve_parallel_vote()

        # Create immutable audit record
        self.env['purchase.approval.history'].sudo().create({
            'purchase_order_id': self.id,
            'approval_level': self.current_approval_level,
            'approver_id': self.env.uid,
            'decision': 'approved',
            'date': fields.Datetime.now(),
            'notes': self.approval_notes or False,
            'matrix_id': self.current_approval_matrix_id.id or False,
        })

        # Check if there is a next approval level
        next_level = self.current_approval_level + 1
        next_matrix = (
            self._get_approval_matrix(level=next_level)
            if self._is_multi_level_enabled()
            else self.env['purchase.approval.matrix']
        )

        if next_matrix:
            # Resolve next-level approver
            if next_matrix.use_hr_manager:
                next_approver = self._get_buyer_hr_manager()
            else:
                next_approver = next_matrix.approver_user_id
            # Resolve delegation for the next level approver
            if next_approver:
                next_approver = next_approver._get_effective_approver()
            next_deadline = False
            if self._is_sla_enabled() and next_matrix.sla_days > 0:
                next_deadline = fields.Datetime.now() + timedelta(days=next_matrix.sla_days)
            self.with_context(approval_workflow_action=True).write({
                'current_approver_id': next_approver.id if next_approver else False,
                'current_approval_level': next_level,
                'current_approval_matrix_id': next_matrix.id,
                'approved_by': self.env.uid,
                'approved_date': fields.Datetime.now(),
                'approval_deadline': next_deadline,
                'approval_token': secrets.token_urlsafe(32),
            })

            approver_label = next_approver.name if next_approver else next_matrix.name
            self.message_post(
                body=Markup('<b>%s</b> approved this RFQ (Level %d). Waiting for <b>%s</b> at Level %d.')
                    % (escape(self.env.user.name), next_level - 1, escape(approver_label), next_level),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            if self._is_activity_enabled():
                self._mark_activity_done()
                self._create_approval_activity(next_matrix)

            if self._is_email_enabled():
                self._send_approval_email()
        else:
            # Final approval reached
            self.with_context(approval_workflow_action=True).write({
                'approval_state': 'approved',
                'approved_by': self.env.uid,
                'approved_date': fields.Datetime.now(),
                'current_approver_id': False,
                'current_approval_matrix_id': False,
                'approval_deadline': False,
                'approval_token': False,
            })

            self.message_post(
                body=Markup('<b>%s</b> gave the final approval. The Purchase Order is ready to be confirmed.')
                    % escape(self.env.user.name),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            if self._is_activity_enabled():
                self._mark_activity_done()

            if self._is_email_enabled():
                self._send_final_approval_email()

            auto_confirm = (
                self._get_param('purchase_approval_workflow.auto_confirm_after_approval', 'False')
                == 'True'
            )
            if auto_confirm:
                self.sudo().with_context(approval_workflow_action=True).button_confirm()

        return True

    def action_reject(self):
        self.ensure_one()

        if not self.can_approve:
            raise UserError(_(
                'You are not authorised to reject this purchase order. '
                'Only the designated approver can take this action.'
            ))

        return {
            'name': _('Rejection Reason'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.approval.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_purchase_order_id': self.id},
        }

    def _do_reject(self, reason):
        """Called from the rejection wizard after validating the mandatory reason."""
        self.ensure_one()

        self.env['purchase.approval.history'].sudo().create({
            'purchase_order_id': self.id,
            'approval_level': self.current_approval_level,
            'approver_id': self.env.uid,
            'decision': 'rejected',
            'date': fields.Datetime.now(),
            'notes': reason,
            'matrix_id': self.current_approval_matrix_id.id or False,
        })

        self.with_context(approval_workflow_action=True).write({
            'approval_state': 'rejected',
            'rejected_by': self.env.uid,
            'rejected_date': fields.Datetime.now(),
            'current_approver_id': False,
            'current_approval_level': 0,
            'current_approval_matrix_id': False,
            'approval_deadline': False,
            'approval_token': False,
        })

        self.message_post(
            body=Markup('<b>%s</b> rejected this RFQ.<br/><b>Reason:</b> %s')
                % (escape(self.env.user.name), escape(reason)),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        if self._is_activity_enabled():
            self._mark_activity_done()

        if self._is_email_enabled():
            self._send_rejection_email(reason)

    def action_reset_for_editing(self):
        """Buyer: unlock a rejected PO so it can be edited before resubmitting."""
        self.ensure_one()
        if self.approval_state != 'rejected':
            return
        self.with_context(approval_workflow_action=True).write({
            'approval_state': 'draft',
            'rejected_by': False,
            'rejected_date': False,
            'current_approver_id': False,
            'current_approval_level': 0,
            'current_approval_matrix_id': False,
            'approval_deadline': False,
        })
        self.message_post(
            body=Markup('<b>%s</b> reset this RFQ for editing after rejection.')
                % escape(self.env.user.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

    def action_view_approval_history(self):
        self.ensure_one()
        return {
            'name': _('Approval History'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.approval.history',
            'view_mode': 'list,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {'default_purchase_order_id': self.id, 'create': False},
        }

    # ------------------------------------------------------------------
    # Mail / Activity helpers
    # ------------------------------------------------------------------

    def _create_approval_activity(self, matrix):
        approver = matrix.approver_user_id
        if not approver:
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        self.activity_schedule(
            activity_type_id=activity_type.id,
            summary=_('Purchase Order Approval Required — %s') % self.name,
            note=_('Purchase order <b>%s</b> (Amount: %s %s) requires your approval at Level %d.')
                % (
                    self.name,
                    self.currency_id.symbol,
                    '{:,.2f}'.format(self.amount_total),
                    self.current_approval_level,
                ),
            user_id=approver.id,
        )

    def _mark_activity_done(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        activities = self.activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and a.user_id == self.env.user
        )
        for activity in activities:
            activity.action_done()

    def _send_submission_email(self):
        template = self.env.ref(
            'purchase_approval_workflow.email_template_po_submission',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(self.id, force_send=False)

    def _send_approval_email(self):
        template = self.env.ref(
            'purchase_approval_workflow.email_template_po_approval_next_level',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(self.id, force_send=False)

    def _send_final_approval_email(self):
        template = self.env.ref(
            'purchase_approval_workflow.email_template_po_final_approval',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(self.id, force_send=False)

    def _send_rejection_email(self, reason):
        template = self.env.ref(
            'purchase_approval_workflow.email_template_po_rejection',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().with_context(rejection_reason=reason).send_mail(
                self.id, force_send=False
            )

    def _send_sla_overdue_email(self):
        template = self.env.ref(
            'purchase_approval_workflow.email_template_po_sla_overdue',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(self.id, force_send=False)

    # ------------------------------------------------------------------
    # SLA cron & escalation
    # ------------------------------------------------------------------

    def _action_approve_parallel_vote(self):
        """Handle a vote for AND-logic (all group members must approve) approval level."""
        self.ensure_one()
        matrix = self.current_approval_matrix_id
        group = matrix.approver_group_id
        level = self.current_approval_level
        user = self.env.user
        now = fields.Datetime.now()

        # Record this user's vote
        existing_vote = self.env['purchase.approval.vote'].sudo().search([
            ('purchase_order_id', '=', self.id),
            ('approval_level', '=', level),
            ('voter_id', '=', user.id),
        ], limit=1)
        if existing_vote:
            existing_vote.sudo().write({'voted': True, 'date': now})
        else:
            self.env['purchase.approval.vote'].sudo().create({
                'purchase_order_id': self.id,
                'approval_level': level,
                'voter_id': user.id,
                'voted': True,
                'date': now,
            })

        # Check if all active group members have voted
        group_members = group.users.filtered(lambda u: not u.share and u.active)
        voted_ids = self.env['purchase.approval.vote'].sudo().search([
            ('purchase_order_id', '=', self.id),
            ('approval_level', '=', level),
            ('voted', '=', True),
        ]).mapped('voter_id.id')

        pending_members = group_members.filtered(lambda u: u.id not in voted_ids)

        if pending_members:
            # Not all voted yet — post progress update
            self.message_post(
                body=Markup(
                    '<b>%s</b> approved this order at Level %d (AND mode). '
                    'Waiting for: <b>%s</b>.'
                ) % (
                    escape(user.name),
                    level,
                    escape(', '.join(pending_members.mapped('name'))),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            return True

        # All members have voted — proceed as a normal approval
        self.env['purchase.approval.history'].sudo().create({
            'purchase_order_id': self.id,
            'approval_level': level,
            'approver_id': self.env.uid,
            'decision': 'approved',
            'date': now,
            'notes': _('Parallel (AND) approval completed — all group members approved.'),
            'matrix_id': matrix.id,
        })
        # Clean up votes
        self.env['purchase.approval.vote'].sudo().search([
            ('purchase_order_id', '=', self.id),
            ('approval_level', '=', level),
        ]).sudo().unlink()

        # Now proceed with normal advance logic
        self.message_post(
            body=Markup('All required approvals received at Level %d. Proceeding to next step.') % level,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        # Advance: check next level
        next_level = level + 1
        next_matrix = (
            self._get_approval_matrix(level=next_level)
            if self._is_multi_level_enabled()
            else self.env['purchase.approval.matrix']
        )
        if next_matrix:
            if next_matrix.use_hr_manager:
                next_approver = self._get_buyer_hr_manager()
            else:
                next_approver = next_matrix.approver_user_id
            if next_approver:
                next_approver = next_approver._get_effective_approver()
            next_deadline = False
            if self._is_sla_enabled() and next_matrix.sla_days > 0:
                next_deadline = fields.Datetime.now() + timedelta(days=next_matrix.sla_days)
            self.with_context(approval_workflow_action=True).write({
                'current_approver_id': next_approver.id if next_approver else False,
                'current_approval_level': next_level,
                'current_approval_matrix_id': next_matrix.id,
                'approved_by': self.env.uid,
                'approved_date': now,
                'approval_deadline': next_deadline,
                'approval_token': secrets.token_urlsafe(32),
            })
            if self._is_activity_enabled():
                self._mark_activity_done()
                self._create_approval_activity(next_matrix)
            if self._is_email_enabled():
                self._send_approval_email()
        else:
            self.with_context(approval_workflow_action=True).write({
                'approval_state': 'approved',
                'approved_by': self.env.uid,
                'approved_date': now,
                'current_approver_id': False,
                'current_approval_matrix_id': False,
                'approval_deadline': False,
                'approval_token': False,
            })
            if self._is_activity_enabled():
                self._mark_activity_done()
            if self._is_email_enabled():
                self._send_final_approval_email()
            auto_confirm = (
                self._get_param('purchase_approval_workflow.auto_confirm_after_approval', 'False')
                == 'True'
            )
            if auto_confirm:
                self.sudo().with_context(approval_workflow_action=True).button_confirm()
        return True

    def action_bulk_approve(self):
        """Server action: approve all selected purchase orders the user is authorised to approve."""
        approved = self.env['purchase.order']
        skipped = []
        for order in self:
            if order.can_approve:
                order.action_approve()
                approved |= order
            else:
                skipped.append(order.name)

        msg = _('%d purchase order(s) approved.') % len(approved)
        if skipped:
            msg += '\n' + _('Skipped (not authorised): %s') % ', '.join(skipped)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Approval Complete'),
                'message': msg,
                'type': 'success' if not skipped else 'warning',
                'sticky': False,
            },
        }

    def _cron_check_approval_sla(self):
        """Daily cron: send escalation notices and reassign overdue approvals."""
        if not self._is_sla_enabled():
            return
        now = fields.Datetime.now()
        overdue = self.search([
            ('approval_state', '=', 'waiting_approval'),
            ('approval_deadline', '!=', False),
            ('approval_deadline', '<', now),
        ])
        for order in overdue:
            order._do_sla_escalation()

    def _do_sla_escalation(self):
        """Send reminder email and optionally reassign to the escalation user."""
        self.ensure_one()
        matrix = self.current_approval_matrix_id
        if not matrix:
            return

        if self._is_email_enabled():
            self._send_sla_overdue_email()

        if matrix.escalate_to_id and matrix.escalate_to_id != self.current_approver_id:
            old_name = self.current_approver_id.name if self.current_approver_id else _('(none)')
            self.with_context(approval_workflow_action=True).write({
                'current_approver_id': matrix.escalate_to_id.id,
            })
            self.message_post(
                body=Markup(
                    '<b>SLA Escalation:</b> Approval deadline passed on <b>%s</b>. '
                    'Approver reassigned from <b>%s</b> to <b>%s</b>.'
                ) % (
                    escape(fields.Datetime.to_string(self.approval_deadline)),
                    escape(old_name),
                    escape(matrix.escalate_to_id.name),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------

    def button_draft(self):
        """Reset to Draft: also clear approval state so the status bar returns to Draft."""
        result = super().button_draft()
        if self._is_workflow_enabled():
            self.with_context(approval_workflow_action=True).write({
                'approval_state': 'draft',
                'current_approver_id': False,
                'current_approval_level': 0,
                'current_approval_matrix_id': False,
                'approval_deadline': False,
            })
        return result

    def button_cancel(self):
        """Cancel: mark activity done and reset approval state to draft."""
        if self._is_activity_enabled():
            for order in self:
                if order.approval_state == 'waiting_approval':
                    order._mark_activity_done()
        result = super().button_cancel()
        if self._is_workflow_enabled():
            self.with_context(approval_workflow_action=True).write({
                'approval_state': 'draft',
                'current_approver_id': False,
                'current_approval_level': 0,
                'current_approval_matrix_id': False,
                'approval_deadline': False,
            })
        return result

    def button_confirm(self):
        if self._is_workflow_enabled():
            is_admin = self.env.user.has_group(
                'purchase_approval_workflow.group_purchase_approval_administrator'
            )
            manager_override = (
                self._get_param('purchase_approval_workflow.allow_manager_override', 'False')
                == 'True'
            )
            is_manager = self.env.user.has_group(
                'purchase_approval_workflow.group_purchase_approval_manager'
            )
            internal_action = self.env.context.get('approval_workflow_action', False)

            for order in self:
                if order.state not in ('draft', 'sent'):
                    continue
                if order.approval_state == 'approved' or internal_action:
                    continue
                if is_admin:
                    continue
                if manager_override and is_manager:
                    continue
                raise UserError(_(
                    'Purchase order "%s" must be approved before it can be confirmed.\n'
                    'Please use the "Submit for Approval" button.'
                ) % order.name)

        result = super().button_confirm()

        if self._is_workflow_enabled():
            for order in self:
                if order.state == 'purchase':
                    order.message_post(
                        body=Markup('<b>%s</b> confirmed the Purchase Order.')
                            % escape(self.env.user.name),
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
        return result

    # Business-content fields that must not change while a PO awaits approval.
    # Everything else (state transitions, tracking, activities, mail, etc.) is allowed.
    _LOCKED_FIELDS_DURING_APPROVAL = frozenset({
        'order_line',
        'partner_id',
        'partner_ref',
        'date_order',
        'date_planned',
        'currency_id',
        'company_id',
        'picking_type_id',
        'dest_address_id',
        'incoterm_id',
        'payment_term_id',
        'fiscal_position_id',
    })

    def write(self, vals):
        if not self.env.context.get('approval_workflow_action') and not self.env.su:
            is_admin = self.env.user.has_group(
                'purchase_approval_workflow.group_purchase_approval_administrator'
            )
            is_manager = self.env.user.has_group(
                'purchase_approval_workflow.group_purchase_approval_manager'
            )
            if not is_admin and not is_manager:
                locked_changes = set(vals.keys()) & self._LOCKED_FIELDS_DURING_APPROVAL
                if locked_changes:
                    for order in self:
                        if (
                            order.approval_state in ('waiting_approval', 'approved', 'rejected')
                            and order._is_workflow_enabled()
                        ):
                            raise UserError(_(
                                'Purchase order "%s" is locked and cannot be edited.\n'
                                'It is currently %s. Use "Reset for Editing" to edit it or "Submit for Approval" to resubmit.'
                            ) % (order.name, dict(order._fields['approval_state'].selection)[order.approval_state]))
        return super().write(vals)

    def unlink(self):
        for order in self:
            if order.approval_state in ('waiting_approval', 'approved'):
                raise UserError(_(
                    'Purchase order "%s" cannot be deleted while in the approval process.\n'
                    'Please reject it first.'
                ) % order.name)
        return super().unlink()

