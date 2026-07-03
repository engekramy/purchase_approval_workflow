# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase


class PurchaseApprovalCommon(TransactionCase):
    """Base test class providing shared fixtures for all approval workflow tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Enable the approval workflow
        cls.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.enabled', 'True'
        )
        cls.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.enable_multi_level', 'True'
        )
        cls.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.enable_email_notifications', 'False'
        )
        cls.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.enable_mail_activities', 'False'
        )
        cls.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.allow_manager_override', 'False'
        )
        cls.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.auto_confirm_after_approval', 'False'
        )

        cls.company = cls.env.ref('base.main_company')

        # Security groups
        cls.group_purchase_user = cls.env.ref('purchase.group_purchase_user')
        cls.group_purchase_manager = cls.env.ref('purchase.group_purchase_manager')
        cls.group_approval_user = cls.env.ref(
            'purchase_approval_workflow.group_purchase_approval_user'
        )
        cls.group_approval_manager = cls.env.ref(
            'purchase_approval_workflow.group_purchase_approval_manager'
        )
        cls.group_approval_admin = cls.env.ref(
            'purchase_approval_workflow.group_purchase_approval_administrator'
        )

        # Users
        cls.buyer = cls._create_user('test_buyer', [cls.group_purchase_user, cls.group_approval_user])
        cls.supervisor = cls._create_user('test_supervisor', [cls.group_approval_manager])
        cls.manager = cls._create_user('test_manager', [cls.group_approval_manager])
        cls.admin_user = cls._create_user('test_approval_admin', [cls.group_approval_admin])

        # Vendor
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Test Vendor',
            'company_type': 'company',
        })

        # Product
        cls.product = cls.env['product.product'].create({
            'name': 'Test Product',
            'purchase_ok': True,
        })

        # Approval matrix — Level 1: Supervisor for small orders (0–5,000)
        cls.matrix_level1_small = cls.env['purchase.approval.matrix'].create({
            'name': 'Supervisor — Small Orders',
            'sequence': 10,
            'company_id': cls.company.id,
            'approval_level': 1,
            'min_amount': 0.0,
            'max_amount': 5000.0,
            'approver_user_id': cls.supervisor.id,
        })

        # Approval matrix — Level 1: Manager for large orders (5,001+)
        cls.matrix_level1_large = cls.env['purchase.approval.matrix'].create({
            'name': 'Manager — Large Orders',
            'sequence': 20,
            'company_id': cls.company.id,
            'approval_level': 1,
            'min_amount': 5001.0,
            'max_amount': 0.0,  # no upper limit
            'approver_user_id': cls.manager.id,
        })

        # Approval matrix — Level 2: Manager (only for large orders)
        cls.matrix_level2 = cls.env['purchase.approval.matrix'].create({
            'name': 'Admin — Level 2',
            'sequence': 10,
            'company_id': cls.company.id,
            'approval_level': 2,
            'min_amount': 5001.0,
            'max_amount': 0.0,
            'approver_user_id': cls.admin_user.id,
        })

    @classmethod
    def _create_user(cls, login, groups):
        user = cls.env['res.users'].create({
            'name': login.replace('_', ' ').title(),
            'login': login + '@test.com',
            'email': login + '@test.com',
            'groups_id': [(6, 0, [g.id for g in groups])],
            'company_ids': [(4, cls.env.ref('base.main_company').id)],
            'company_id': cls.env.ref('base.main_company').id,
        })
        return user

    def _create_po(self, amount=1000.0, user=None):
        """Create a draft purchase order with a single line."""
        user = user or self.buyer
        po = self.env['purchase.order'].with_user(user).create({
            'partner_id': self.vendor.id,
            'company_id': self.company.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 1.0,
                'price_unit': amount,
                'product_uom': self.product.uom_po_id.id,
                'name': self.product.name,
                'date_planned': '2026-07-10',
            })],
        })
        return po
