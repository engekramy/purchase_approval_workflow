# -*- coding: utf-8 -*-
"""Approval Policy Template Wizard — create pre-built matrix configurations."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# Pre-built policy definitions
_POLICIES = {
    'simple_1level': {
        'label': 'Simple (1 Level — Manager Approval)',
        'rules': [
            {'name': 'Manager Approval', 'level': 1, 'min': 0, 'max': 0},
        ],
    },
    'two_level': {
        'label': 'Two-Level (Supervisor → Manager)',
        'rules': [
            {'name': 'Supervisor Approval', 'level': 1, 'min': 0, 'max': 10000},
            {'name': 'Manager Approval', 'level': 2, 'min': 10000, 'max': 0},
        ],
    },
    'three_level': {
        'label': 'Three-Level (Supervisor → Manager → Director)',
        'rules': [
            {'name': 'Supervisor Approval', 'level': 1, 'min': 0, 'max': 5000},
            {'name': 'Manager Approval', 'level': 2, 'min': 5000, 'max': 50000},
            {'name': 'Director Approval', 'level': 3, 'min': 50000, 'max': 0},
        ],
    },
    'amount_based': {
        'label': 'Amount-Based (Low / Medium / High)',
        'rules': [
            {'name': 'Low-Value — Auto-Route', 'level': 1, 'min': 0, 'max': 1000},
            {'name': 'Medium-Value Approval', 'level': 1, 'min': 1000, 'max': 25000},
            {'name': 'High-Value Approval', 'level': 2, 'min': 25000, 'max': 0},
        ],
    },
}


class PurchaseApprovalPolicyWizard(models.TransientModel):
    _name = 'purchase.approval.policy.wizard'
    _description = 'Approval Policy Template Wizard'

    policy_type = fields.Selection(
        selection=[
            ('simple_1level', 'Simple (1 Level — Manager Approval)'),
            ('two_level', 'Two-Level (Supervisor → Manager)'),
            ('three_level', 'Three-Level (Supervisor → Manager → Director)'),
            ('amount_based', 'Amount-Based (Low / Medium / High)'),
        ],
        string='Policy Template',
        required=True,
        default='two_level',
        help='Select a pre-built approval policy to create the matrix rules automatically.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    clear_existing = fields.Boolean(
        string='Archive Existing Rules',
        default=False,
        help='Archive all existing active rules for this company before creating the new policy.',
    )

    def action_apply(self):
        self.ensure_one()
        policy = _POLICIES.get(self.policy_type)
        if not policy:
            raise UserError(_('Unknown policy template.'))

        Matrix = self.env['purchase.approval.matrix']

        if self.clear_existing:
            existing = Matrix.search([
                ('company_id', '=', self.company_id.id),
                ('active', '=', True),
            ])
            existing.write({'active': False})

        created = 0
        for rule_def in policy['rules']:
            Matrix.create({
                'name': rule_def['name'],
                'approval_level': rule_def['level'],
                'company_id': self.company_id.id,
                'min_amount': rule_def['min'],
                'max_amount': rule_def['max'],
                'approver_user_id': self.env.uid,  # placeholder — user should update
                'sequence': 10 * rule_def['level'],
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Policy Applied'),
                'message': _(
                    'Created %d rule(s) from the "%s" template. '
                    'Please assign the correct approvers to each rule.'
                ) % (created, policy['label']),
                'type': 'success',
                'sticky': True,
            },
        }
