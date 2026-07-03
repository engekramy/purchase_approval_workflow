# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PurchaseApprovalMatrix(models.Model):
    _name = 'purchase.approval.matrix'
    _description = 'Purchase Approval Matrix'
    _order = 'sequence asc, id asc'

    name = fields.Char(string='Rule Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )

    min_amount = fields.Monetary(
        string='Minimum Amount',
        currency_field='currency_id',
        default=0.0,
        help='Minimum purchase order total (in company currency). '
             'Leave at 0 for no lower limit.',
    )
    max_amount = fields.Monetary(
        string='Maximum Amount',
        currency_field='currency_id',
        default=0.0,
        help='Maximum purchase order total (in company currency). '
             'Set to 0 for no upper limit.',
    )

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain=[('supplier_rank', '>', 0)],
        help='Restrict this rule to orders from a specific vendor. '
             'Leave empty to apply to all vendors.',
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        help='Leave empty to apply to all departments.',
    )
    product_category_id = fields.Many2one(
        'product.category',
        string='Product Category',
        help='Leave empty to apply to all product categories. '
             'Matches if any order line belongs to this category or its children.',
    )

    approver_user_id = fields.Many2one(
        'res.users',
        string='Approver (User)',
        help='Specific user who must approve this level. '
             'Takes priority over Approver Group if both are set.',
        domain=[('share', '=', False)],
    )
    approver_group_id = fields.Many2one(
        'res.groups',
        string='Approver (Group)',
        help='Any active user in this group can approve this level. '
             'Used when no specific Approver User is set.',
    )
    use_hr_manager = fields.Boolean(
        string='Use Buyer\'s HR Manager',
        default=False,
        help='When enabled, the system automatically routes this approval level '
             'to the HR manager of the employee who created the purchase order. '
             'Overrides the Approver User / Group settings.',
    )
    approval_type = fields.Selection(
        selection=[
            ('any', 'Any One Approver (OR)'),
            ('all', 'All Group Members (AND)'),
        ],
        string='Approval Logic',
        default='any',
        required=True,
        help='"Any One Approver" means the first person in the group to act advances the workflow. '
             '"All Group Members" requires every active group member to approve before advancing.',
    )

    approval_level = fields.Integer(
        string='Approval Level',
        required=True,
        default=1,
        help='Level 1 is the first approval required. '
             'Level 2 requires Level 1 to be approved first, and so on.',
    )

    # Friendly Selection alias for the form statusbar (synced with approval_level)
    level_selection = fields.Selection(
        selection=[
            ('1',  'Level 1'),  ('2',  'Level 2'),  ('3',  'Level 3'),
            ('4',  'Level 4'),  ('5',  'Level 5'),  ('6',  'Level 6'),
            ('7',  'Level 7'),  ('8',  'Level 8'),  ('9',  'Level 9'),
            ('10', 'Level 10'),
        ],
        string='Approval Level',
        compute='_compute_level_selection',
        inverse='_set_level_selection',
        store=False,
    )

    @api.depends('approval_level')
    def _compute_level_selection(self):
        for rule in self:
            lvl = rule.approval_level
            rule.level_selection = str(lvl) if 1 <= lvl <= 10 else '1'

    def _set_level_selection(self):
        for rule in self:
            if rule.level_selection:
                rule.approval_level = int(rule.level_selection)

    sla_days = fields.Integer(
        string='Deadline (Days)',
        default=0,
        help='Number of calendar days the approver has to act at this level. '
             '0 means no deadline. When overdue, a reminder email is sent and '
             'the order is reassigned to the Escalate To user (if set).',
    )
    escalate_to_id = fields.Many2one(
        'res.users',
        string='Escalate To',
        domain=[('share', '=', False)],
        help='If the approval is not completed within the SLA deadline, '
             'this user is notified and becomes the new approver automatically.',
    )

    notes = fields.Text(string='Notes')

    @api.constrains('approver_user_id', 'approver_group_id', 'use_hr_manager')
    def _check_approver(self):
        for rule in self:
            if not rule.use_hr_manager and not rule.approver_user_id and not rule.approver_group_id:
                raise ValidationError(_(
                    'Rule "%s" must have either an Approver User, an Approver Group, '
                    'or "Use Buyer\'s HR Manager" enabled.'
                ) % rule.name)

    @api.constrains('min_amount', 'max_amount')
    def _check_amounts(self):
        for rule in self:
            if rule.max_amount and rule.min_amount > rule.max_amount:
                raise ValidationError(_(
                    'Rule "%s": Minimum Amount cannot be greater than Maximum Amount.'
                ) % rule.name)

    @api.constrains('approval_level')
    def _check_approval_level(self):
        for rule in self:
            if rule.approval_level < 1:
                raise ValidationError(_(
                    'Approval Level must be 1 or greater.'
                ))

    # Color driven by level — used in kanban cards and the diagram wizard
    level_color = fields.Char(
        string='Level Color',
        compute='_compute_level_color',
        store=False,
    )

    _LEVEL_COLORS = [
        '#4472C4',  # 1 – blue
        '#198754',  # 2 – green
        '#ED7D31',  # 3 – orange
        '#875A7B',  # 4 – brand purple
        '#DC3545',  # 5 – red
        '#0B85A0',  # 6 – teal
        '#6F42C1',  # 7 – violet
        '#20C997',  # 8 – mint
        '#D4860A',  # 9 – amber
        '#495057',  # 10 – charcoal
    ]

    @api.depends('approval_level')
    def _compute_level_color(self):
        for rule in self:
            idx = (rule.approval_level - 1) % len(self._LEVEL_COLORS)
            rule.level_color = self._LEVEL_COLORS[idx]

    @api.depends('name', 'approval_level')
    def _compute_display_name(self):
        for rule in self:
            label = rule.name or _('New Rule')
            rule.display_name = '%s (Level %d)' % (label, rule.approval_level)
