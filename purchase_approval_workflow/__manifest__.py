# -*- coding: utf-8 -*-
{
    'name': 'Purchase Approval Workflow',
    'version': '19.0.4.0.0',
    'category': 'Purchase',
    'summary': 'Configurable multi-level purchase order approval workflow',
    'description': """
Purchase Approval Workflow
==========================
Introduces a fully configurable, multi-level purchase order approval workflow
with 14 advanced features for enterprise-grade procurement governance.

Key Features:
1.  SLA & Escalation: per-level deadline, overdue badge, automatic escalation cron
2.  One-Click Email Approval: tokenized Approve/Reject buttons in notification emails
3.  Bulk Approval Dashboard: My/All Pending Approvals with inline actions and bulk server action
4.  Delegation / Out-of-Office: delegate approvals to another user with an optional end date
5.  Trusted Vendor Bypass: skip workflow for trusted vendors below a configurable amount limit
6.  Parallel Approval (AND logic): require all group members to approve before advancing
7.  HR Manager Auto-Routing: automatically route to the buyer's HR manager hierarchy
8.  Budget Check Integration: real-time remaining budget warning on PO approval screen
9.  Approval Analytics Dashboard: pivot + bar/trend graph views on approval history
10. Change Summary on Resubmission: automatic chatter diff of what changed since last submission
11. Approval Policy Templates: wizard to create pre-built matrix configurations in one click
12. Vendor-Specific Rules: restrict matrix rules to a specific vendor
13. Urgency Override: mark POs as Urgent or Critical to fast-track or escalate routing
14. Export Audit Trail: download the full audit trail as a formatted Excel file or branded PDF
    """,
    'author': 'Eng. Ekramy Mohamed',
    'website': 'https://apps.odoo.com/apps/modules/19.0/purchase_approval_workflow/',
    'support': 'engekramy_mohamed@hotmail.com',
    'license': 'OPL-1',
    'price': 49.50,
    'currency': 'USD',
    'icon': 'purchase_approval_workflow/static/description/icon.png',
    'images': ['static/description/sc1_po_list.png'],
    'depends': [
        'purchase',
        'mail',
        'hr',
    ],
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/mail_template_data.xml',
        'data/cron_data.xml',
        'views/purchase_approval_matrix_diagram_views.xml',
        'views/purchase_approval_matrix_views.xml',
        'views/purchase_approval_history_views.xml',
        'views/purchase_approval_reject_wizard_views.xml',
        'views/purchase_order_views.xml',
        'views/purchase_approval_dashboard_views.xml',
        'views/res_users_views.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/purchase_approval_analytics_views.xml',
        'views/purchase_approval_policy_wizard_views.xml',
        'views/purchase_approval_audit_export_wizard_views.xml',
        'views/purchase_approval_audit_trail_report.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
