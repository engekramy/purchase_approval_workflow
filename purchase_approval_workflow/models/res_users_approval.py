# -*- coding: utf-8 -*-
"""Approval delegation / Out-of-Office extension for res.users."""
from odoo import api, fields, models, _


class ResUsersApprovalDelegation(models.Model):
    _inherit = 'res.users'

    # ------------------------------------------------------------------
    # Delegation fields
    # ------------------------------------------------------------------

    approval_delegate_id = fields.Many2one(
        'res.users',
        string='Approval Delegate',
        domain=[('share', '=', False)],
        help='While you are out of office, pending approval requests will be '
             'automatically reassigned to this person.',
    )
    approval_delegate_until = fields.Date(
        string='Delegate Until',
        help='Delegation is active until this date (inclusive). '
             'Leave empty for indefinite delegation.',
    )

    # ------------------------------------------------------------------
    # Computed helper
    # ------------------------------------------------------------------

    is_on_approval_leave = fields.Boolean(
        compute='_compute_is_on_approval_leave',
        string='On Approval Leave',
        store=False,
    )

    @api.depends('approval_delegate_id', 'approval_delegate_until')
    def _compute_is_on_approval_leave(self):
        today = fields.Date.today()
        for user in self:
            if not user.approval_delegate_id:
                user.is_on_approval_leave = False
            elif not user.approval_delegate_until:
                user.is_on_approval_leave = True
            else:
                user.is_on_approval_leave = user.approval_delegate_until >= today

    # ------------------------------------------------------------------
    # API for purchase_order.py
    # ------------------------------------------------------------------

    def _get_effective_approver(self):
        """Return self or the active delegate if the user is on leave."""
        self.ensure_one()
        if self.is_on_approval_leave and self.approval_delegate_id:
            return self.approval_delegate_id
        return self
