# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from .common import PurchaseApprovalCommon


class TestPurchaseApprovalWorkflow(PurchaseApprovalCommon):
    """Comprehensive tests for the purchase approval workflow."""

    # ------------------------------------------------------------------
    # 1. Draft submission
    # ------------------------------------------------------------------

    def test_01_initial_state(self):
        """New PO must have approval_state = 'draft'."""
        po = self._create_po()
        self.assertEqual(po.approval_state, 'draft')
        self.assertEqual(po.state, 'draft')
        self.assertFalse(po.submitted_by)

    def test_02_submit_for_approval_small_order(self):
        """Submitting a small order assigns the supervisor as approver."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        self.assertEqual(po.approval_state, 'waiting_approval')
        self.assertEqual(po.submitted_by, self.buyer)
        self.assertTrue(po.submitted_date)
        self.assertEqual(po.current_approval_level, 1)
        self.assertEqual(po.current_approver_id, self.supervisor)
        self.assertEqual(po.current_approval_matrix_id, self.matrix_level1_small)

    def test_03_submit_for_approval_large_order(self):
        """Submitting a large order assigns the manager as level-1 approver."""
        po = self._create_po(amount=10000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        self.assertEqual(po.approval_state, 'waiting_approval')
        self.assertEqual(po.current_approver_id, self.manager)
        self.assertEqual(po.current_approval_matrix_id, self.matrix_level1_large)

    def test_04_cannot_submit_empty_po(self):
        """Submitting a PO without order lines must raise UserError."""
        po = self.env['purchase.order'].with_user(self.buyer).create({
            'partner_id': self.vendor.id,
        })
        with self.assertRaises(UserError):
            po.action_submit_for_approval()

    def test_05_no_matrix_raises_validation_error(self):
        """A PO with no matching matrix rule must raise ValidationError."""
        # Remove all matrix rules temporarily
        self.matrix_level1_small.active = False
        self.matrix_level1_large.active = False

        po = self._create_po(amount=1000.0)
        with self.assertRaises(ValidationError):
            po.with_user(self.buyer).action_submit_for_approval()

        # Restore
        self.matrix_level1_small.active = True
        self.matrix_level1_large.active = True

    # ------------------------------------------------------------------
    # 2. Approval flow
    # ------------------------------------------------------------------

    def test_06_single_level_approval(self):
        """Small order: supervisor approves → approval_state becomes 'approved'."""
        # Matrix level 2 has min_amount 5001, so small orders skip it
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        po.with_user(self.supervisor).action_approve()

        self.assertEqual(po.approval_state, 'approved')
        self.assertEqual(po.approved_by, self.supervisor)
        self.assertTrue(po.approved_date)
        self.assertFalse(po.current_approver_id)
        # Audit record created
        self.assertEqual(len(po.approval_history_ids), 1)
        self.assertEqual(po.approval_history_ids[0].decision, 'approved')
        self.assertEqual(po.approval_history_ids[0].approver_id, self.supervisor)

    def test_07_confirm_after_approval(self):
        """After approval, buyer can confirm the PO."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        po.with_user(self.supervisor).action_approve()

        po.with_user(self.buyer).button_confirm()
        self.assertEqual(po.state, 'purchase')

    def test_08_cannot_confirm_without_approval(self):
        """Buyer cannot confirm a PO that has not been approved."""
        po = self._create_po(amount=1000.0)
        # Still in draft, not submitted
        with self.assertRaises(UserError):
            po.with_user(self.buyer).button_confirm()

    def test_09_cannot_confirm_while_waiting(self):
        """Buyer cannot confirm a PO that is waiting for approval."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        with self.assertRaises(UserError):
            po.with_user(self.buyer).button_confirm()

    # ------------------------------------------------------------------
    # 3. Rejection
    # ------------------------------------------------------------------

    def test_10_rejection_returns_to_draft(self):
        """Rejection resets approval_state to draft and records the reason."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        po.with_user(self.supervisor)._do_reject('Price too high.')

        self.assertEqual(po.approval_state, 'draft')
        self.assertEqual(po.rejected_by, self.supervisor)
        self.assertTrue(po.rejected_date)
        self.assertFalse(po.current_approver_id)
        self.assertEqual(po.current_approval_level, 0)
        # Audit record
        self.assertEqual(len(po.approval_history_ids), 1)
        self.assertEqual(po.approval_history_ids[0].decision, 'rejected')
        self.assertEqual(po.approval_history_ids[0].notes, 'Price too high.')

    def test_11_can_resubmit_after_rejection(self):
        """After rejection, buyer can resubmit for approval."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        po.with_user(self.supervisor)._do_reject('Please revise.')

        # Resubmit
        po.with_user(self.buyer).action_submit_for_approval()
        self.assertEqual(po.approval_state, 'waiting_approval')
        # Two history records now
        self.assertEqual(len(po.approval_history_ids), 1)  # only rejection so far

    def test_12_audit_records_are_immutable(self):
        """Non-sudo users cannot write or delete approval history records."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        po.with_user(self.supervisor).action_approve()

        history = po.approval_history_ids[0]
        # Regular users (non-sudo) must be blocked
        with self.assertRaises(UserError):
            history.with_user(self.buyer).write({'notes': 'tampered'})
        with self.assertRaises(UserError):
            history.with_user(self.buyer).unlink()

    # ------------------------------------------------------------------
    # 4. Multi-level approval
    # ------------------------------------------------------------------

    def test_13_multi_level_approval(self):
        """Large order requires level 1 (manager) then level 2 (admin)."""
        po = self._create_po(amount=10000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        self.assertEqual(po.current_approval_level, 1)
        self.assertEqual(po.current_approver_id, self.manager)

        # Level 1 approval
        po.with_user(self.manager).action_approve()
        self.assertEqual(po.approval_state, 'waiting_approval')  # still waiting
        self.assertEqual(po.current_approval_level, 2)
        self.assertEqual(po.current_approver_id, self.admin_user)

        # Level 2 approval
        po.with_user(self.admin_user).action_approve()
        self.assertEqual(po.approval_state, 'approved')
        self.assertFalse(po.current_approver_id)

        # Two approval history records
        self.assertEqual(len(po.approval_history_ids), 2)
        levels = po.approval_history_ids.mapped('approval_level')
        self.assertIn(1, levels)
        self.assertIn(2, levels)

    def test_14_multi_level_wrong_approver_at_level2(self):
        """The level-1 approver cannot also approve at level 2."""
        po = self._create_po(amount=10000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        po.with_user(self.manager).action_approve()  # Level 1 done

        # manager tries to approve level 2 (but admin_user is the level-2 approver)
        with self.assertRaises(UserError):
            po.with_user(self.manager).action_approve()

    # ------------------------------------------------------------------
    # 5. Permission validation
    # ------------------------------------------------------------------

    def test_15_buyer_cannot_approve(self):
        """A purchase user who is not the designated approver cannot approve."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        with self.assertRaises(UserError):
            po.with_user(self.buyer).action_approve()

    def test_16_wrong_approver_cannot_approve(self):
        """A user who is not the current approver and not manager/admin cannot approve."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        # supervisor is the approver; manager is not the current approver
        with self.assertRaises(UserError):
            po.with_user(self.manager).action_approve()

    def test_17_cannot_edit_po_while_waiting(self):
        """A purchase user cannot edit a PO while it is waiting for approval."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        with self.assertRaises(UserError):
            po.with_user(self.buyer).write({'notes': 'trying to edit'})

    def test_18_cannot_delete_po_while_waiting(self):
        """A purchase user cannot delete a PO while it is waiting for approval."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()

        with self.assertRaises(UserError):
            po.with_user(self.buyer).unlink()

    # ------------------------------------------------------------------
    # 6. Manager override
    # ------------------------------------------------------------------

    def test_19_manager_override_allows_approval(self):
        """When manager override is enabled, any manager can approve."""
        self.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.allow_manager_override', 'True'
        )
        try:
            po = self._create_po(amount=1000.0)
            po.with_user(self.buyer).action_submit_for_approval()
            # manager is NOT the current approver (supervisor is), but override is on
            po.with_user(self.manager).action_approve()
            self.assertEqual(po.approval_state, 'approved')
        finally:
            self.env['ir.config_parameter'].sudo().set_param(
                'purchase_approval_workflow.allow_manager_override', 'False'
            )

    def test_20_admin_can_always_approve(self):
        """Administrator can approve any order regardless of matrix assignment."""
        po = self._create_po(amount=1000.0)
        po.with_user(self.buyer).action_submit_for_approval()
        # admin_user is administrator group, supervisor is the matrix approver
        po.with_user(self.admin_user).action_approve()
        self.assertEqual(po.approval_state, 'approved')

    def test_21_manager_can_confirm_with_override(self):
        """When override is enabled, manager can confirm without going through approval."""
        self.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.allow_manager_override', 'True'
        )
        try:
            po = self._create_po(amount=1000.0)
            po.with_user(self.manager).button_confirm()
            self.assertEqual(po.state, 'purchase')
        finally:
            self.env['ir.config_parameter'].sudo().set_param(
                'purchase_approval_workflow.allow_manager_override', 'False'
            )

    # ------------------------------------------------------------------
    # 7. Workflow disabled
    # ------------------------------------------------------------------

    def test_22_workflow_disabled_allows_direct_confirm(self):
        """When workflow is disabled, buyers can confirm directly."""
        self.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.enabled', 'False'
        )
        try:
            po = self._create_po(amount=1000.0)
            po.with_user(self.buyer).button_confirm()
            self.assertEqual(po.state, 'purchase')
        finally:
            self.env['ir.config_parameter'].sudo().set_param(
                'purchase_approval_workflow.enabled', 'True'
            )

    # ------------------------------------------------------------------
    # 8. Auto-confirm after final approval
    # ------------------------------------------------------------------

    def test_23_auto_confirm_after_approval(self):
        """When auto-confirm is enabled, PO is confirmed automatically after final approval."""
        self.env['ir.config_parameter'].sudo().set_param(
            'purchase_approval_workflow.auto_confirm_after_approval', 'True'
        )
        try:
            po = self._create_po(amount=1000.0)
            po.with_user(self.buyer).action_submit_for_approval()
            po.with_user(self.supervisor).action_approve()
            # Should be confirmed automatically
            self.assertEqual(po.state, 'purchase')
        finally:
            self.env['ir.config_parameter'].sudo().set_param(
                'purchase_approval_workflow.auto_confirm_after_approval', 'False'
            )

    # ------------------------------------------------------------------
    # 9. Approval matrix validation
    # ------------------------------------------------------------------

    def test_24_matrix_requires_approver(self):
        """Matrix rule without approver user or group must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['purchase.approval.matrix'].create({
                'name': 'Bad Rule',
                'company_id': self.company.id,
                'approval_level': 1,
                'min_amount': 0.0,
                'max_amount': 1000.0,
                # No approver_user_id and no approver_group_id
            })

    def test_25_matrix_min_greater_than_max_raises(self):
        """Matrix with min_amount > max_amount must raise ValidationError."""
        with self.assertRaises(ValidationError):
            self.env['purchase.approval.matrix'].create({
                'name': 'Invalid Amounts',
                'company_id': self.company.id,
                'approval_level': 1,
                'min_amount': 9000.0,
                'max_amount': 1000.0,
                'approver_user_id': self.supervisor.id,
            })

    def test_26_display_state_transitions(self):
        """display_state reflects the correct stage at each workflow step."""
        po = self._create_po(amount=1000.0)
        self.assertEqual(po.display_state, 'draft')

        po.with_user(self.buyer).action_submit_for_approval()
        self.assertEqual(po.display_state, 'waiting_approval')

        po.with_user(self.supervisor).action_approve()
        self.assertEqual(po.display_state, 'approved')

        po.with_user(self.buyer).button_confirm()
        self.assertEqual(po.display_state, 'purchase')

    def test_27_approval_history_count_smart_button(self):
        """approval_history_count increments with each approval decision."""
        po = self._create_po(amount=10000.0)
        self.assertEqual(po.approval_history_count, 0)

        po.with_user(self.buyer).action_submit_for_approval()
        po.with_user(self.manager).action_approve()
        self.assertEqual(po.approval_history_count, 1)

        po.with_user(self.admin_user).action_approve()
        self.assertEqual(po.approval_history_count, 2)
