# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseApprovalRejectWizard(models.TransientModel):
    _name = 'purchase.approval.reject.wizard'
    _description = 'Purchase Order Rejection Wizard'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        readonly=True,
    )
    purchase_order_name = fields.Char(
        string='PO Reference',
        related='purchase_order_id.name',
        readonly=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        related='purchase_order_id.partner_id',
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='Total Amount',
        related='purchase_order_id.amount_total',
        currency_field='currency_id',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='purchase_order_id.currency_id',
        readonly=True,
    )
    current_level = fields.Integer(
        string='Current Approval Level',
        related='purchase_order_id.current_approval_level',
        readonly=True,
    )
    reason = fields.Text(
        string='Rejection Reason',
        required=True,
        help='Provide a clear reason for rejection. This will be recorded '
             'permanently in the approval history and communicated to the buyer.',
    )

    @api.constrains('reason')
    def _check_reason(self):
        for wizard in self:
            if not wizard.reason or not wizard.reason.strip():
                raise UserError(_('A rejection reason is mandatory.'))

    def action_confirm_rejection(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_('Please provide a rejection reason before confirming.'))
        self.purchase_order_id._do_reject(self.reason.strip())
        return {'type': 'ir.actions.act_window_close'}
