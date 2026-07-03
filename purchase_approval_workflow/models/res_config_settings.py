# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    purchase_approval_enabled = fields.Boolean(
        string='Enable Purchase Approval Workflow',
        config_parameter='purchase_approval_workflow.enabled',
        help='When enabled, purchase users must submit RFQs for approval before '
             'they can be confirmed as Purchase Orders.',
    )
    purchase_approval_multi_level = fields.Boolean(
        string='Enable Multi-Level Approval',
        config_parameter='purchase_approval_workflow.enable_multi_level',
        help='When enabled, the system checks for additional approval levels '
             'after each approval until all levels are satisfied.',
    )
    purchase_approval_email_notifications = fields.Boolean(
        string='Enable Email Notifications',
        config_parameter='purchase_approval_workflow.enable_email_notifications',
        help='Automatically send emails to approvers and submitters at each workflow step.',
    )
    purchase_approval_mail_activities = fields.Boolean(
        string='Enable Mail Activities',
        config_parameter='purchase_approval_workflow.enable_mail_activities',
        help='Create a scheduled activity assigned to the current approver when '
             'a purchase order is submitted for approval.',
    )
    purchase_approval_manager_override = fields.Boolean(
        string='Allow Manager Override',
        config_parameter='purchase_approval_workflow.allow_manager_override',
        help='When enabled, users in the Purchase Approval Manager group can '
             'approve any purchase order, not just those assigned to them.',
    )
    purchase_approval_auto_confirm = fields.Boolean(
        string='Auto-Confirm After Final Approval',
        config_parameter='purchase_approval_workflow.auto_confirm_after_approval',
        help='When enabled, the purchase order is automatically confirmed as a '
             'Purchase Order immediately after receiving the final approval.',
    )
    purchase_approval_sla_enabled = fields.Boolean(
        string='Enable Approval SLA & Escalation',
        config_parameter='purchase_approval_workflow.enable_sla',
        help='When enabled, each approval matrix rule can specify a deadline in days. '
             'A daily cron job checks for overdue approvals, sends reminder emails, '
             'and reassigns the order to the configured escalation user.',
    )
    purchase_approval_trusted_vendor_bypass = fields.Boolean(
        string='Enable Trusted Vendor Bypass',
        config_parameter='purchase_approval_workflow.enable_trusted_vendor_bypass',
        help='When enabled, purchase orders from vendors marked as "Trusted" are '
             'automatically approved without going through the approval workflow.',
    )
    purchase_approval_budget_check = fields.Boolean(
        string='Enable Budget Check on Approval',
        config_parameter='purchase_approval_workflow.enable_budget_check',
        help='When enabled, the remaining analytic budget is displayed on the PO '
             'during the approval process. Requires the Budget Management module.',
    )
