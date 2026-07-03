# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseApprovalHistory(models.Model):
    _name = 'purchase.approval.history'
    _description = 'Purchase Approval History'
    _order = 'date asc, id asc'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        ondelete='cascade',
        index=True,
        readonly=True,
    )
    purchase_order_name = fields.Char(
        string='PO Reference',
        related='purchase_order_id.name',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='purchase_order_id.company_id',
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        related='purchase_order_id.partner_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='purchase_order_id.currency_id',
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='PO Amount',
        related='purchase_order_id.amount_total',
        readonly=True,
        currency_field='currency_id',
    )

    approval_level = fields.Integer(
        string='Approval Level',
        required=True,
        readonly=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
        readonly=True,
    )
    decision = fields.Selection(
        [
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Decision',
        required=True,
        readonly=True,
    )
    date = fields.Datetime(
        string='Decision Date',
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    notes = fields.Text(string='Notes / Reason', readonly=True)

    matrix_id = fields.Many2one(
        'purchase.approval.matrix',
        string='Approval Rule',
        readonly=True,
        ondelete='set null',
    )

    def unlink(self):
        # Allow SQL-level cascade (from PO deletion) to pass; block explicit UI deletes.
        if not self.env.su:
            raise UserError(_(
                'Approval history records cannot be deleted. '
                'They are permanent audit trail entries.'
            ))
        return super().unlink()

    def write(self, vals):
        # Allow the ORM to recompute stored related fields (runs as sudo).
        # Block any explicit user-initiated modifications.
        if not self.env.su:
            raise UserError(_(
                'Approval history records cannot be modified. '
                'They are permanent audit trail entries.'
            ))
        return super().write(vals)
