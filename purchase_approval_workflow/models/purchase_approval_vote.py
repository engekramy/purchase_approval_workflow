# -*- coding: utf-8 -*-
"""Parallel approval vote tracking — used for AND-logic (all-must-approve) levels."""
from odoo import fields, models


class PurchaseApprovalVote(models.Model):
    _name = 'purchase.approval.vote'
    _description = 'Purchase Approval Parallel Vote'
    _order = 'date asc'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    approval_level = fields.Integer(string='Level', required=True)
    voter_id = fields.Many2one(
        'res.users',
        string='Voter',
        required=True,
        ondelete='restrict',
    )
    voted = fields.Boolean(string='Voted', default=False)
    date = fields.Datetime(string='Vote Date')
    notes = fields.Text(string='Notes')
