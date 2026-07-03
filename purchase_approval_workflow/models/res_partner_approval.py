# -*- coding: utf-8 -*-
"""Trusted-vendor bypass extension for res.partner."""
from odoo import fields, models


class ResPartnerApproval(models.Model):
    _inherit = 'res.partner'

    approval_bypass = fields.Boolean(
        string='Trusted Vendor (Skip Approval)',
        default=False,
        help='When enabled, purchase orders from this vendor are automatically '
             'approved without going through the normal approval workflow.',
    )
    approval_bypass_limit = fields.Monetary(
        string='Bypass Limit',
        currency_field='currency_id',
        default=0.0,
        help='Maximum order amount that qualifies for auto-bypass. '
             '0.00 means no limit — all orders from this vendor are auto-approved.',
    )
