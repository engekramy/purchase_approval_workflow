# -*- coding: utf-8 -*-
"""HTTP controller for one-click email approve/reject links."""
import html
import logging

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class PurchaseApprovalController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_order_by_token(self, token):
        if not token or len(token) < 40:
            return None
        return request.env['purchase.order'].sudo().search([
            ('approval_token', '=', token),
            ('approval_state', '=', 'waiting_approval'),
        ], limit=1) or None

    # ------------------------------------------------------------------
    # Approve
    # ------------------------------------------------------------------

    @http.route(
        '/purchase-approval/<string:token>/approve',
        type='http', auth='public', csrf=False,
    )
    def email_approve(self, token, **kwargs):
        order = self._get_order_by_token(token)
        if not order:
            return self._render_result('invalid', order=None)

        approver = order.current_approver_id
        if not approver:
            return self._render_result('invalid', order=order)

        sudo_order = order.with_user(approver.id)
        if not sudo_order.can_approve:
            return self._render_result('already_processed', order=order, approver=approver)

        try:
            sudo_order.action_approve()
            return self._render_result('approved', order=order, approver=approver)
        except Exception:
            _logger.exception("Email approval failed for PO %s", order.name)
            return self._render_result('error', order=order)

    # ------------------------------------------------------------------
    # Reject – GET shows form, POST submits it
    # ------------------------------------------------------------------

    @http.route(
        '/purchase-approval/<string:token>/reject',
        type='http', auth='public', csrf=False, methods=['GET'],
    )
    def email_reject_form(self, token, **kwargs):
        order = self._get_order_by_token(token)
        if not order:
            return self._render_result('invalid', order=None)

        approver = order.current_approver_id
        if not approver:
            return self._render_result('invalid', order=order)

        sudo_order = order.with_user(approver.id)
        if not sudo_order.can_approve:
            return self._render_result('already_processed', order=order, approver=approver)

        return self._render_result('reject_form', order=order, approver=approver, token=token)

    @http.route(
        '/purchase-approval/<string:token>/reject',
        type='http', auth='public', csrf=False, methods=['POST'],
    )
    def email_reject_submit(self, token, reason='', **kwargs):
        order = self._get_order_by_token(token)
        if not order:
            return self._render_result('invalid', order=None)

        approver = order.current_approver_id
        if not approver:
            return self._render_result('invalid', order=order)

        sudo_order = order.with_user(approver.id)
        if not sudo_order.can_approve:
            return self._render_result('already_processed', order=order, approver=approver)

        reason = (reason or '').strip() or _('Rejected via email.')
        sudo_order._do_reject(reason)
        return self._render_result('rejected', order=order, approver=approver, reason=reason)

    # ------------------------------------------------------------------
    # HTML renderer — no QWeb/website dependency needed
    # ------------------------------------------------------------------

    _STYLE = """
<style>
  body{font-family:Arial,sans-serif;background:#f4f6f9;display:flex;
       justify-content:center;align-items:center;min-height:100vh;margin:0;}
  .card{background:#fff;border-radius:8px;box-shadow:0 2px 16px rgba(0,0,0,.12);
        max-width:520px;width:94%;padding:40px 36px;text-align:center;}
  .icon{font-size:56px;margin-bottom:16px;}
  h2{margin:0 0 12px;}
  p{color:#555;margin:0 0 20px;line-height:1.6;}
  .badge{display:inline-block;padding:4px 12px;border-radius:20px;
         font-weight:bold;font-size:13px;margin:4px 0;}
  .green{background:#d4edda;color:#155724;}
  .red{background:#f8d7da;color:#721c24;}
  .yellow{background:#fff3cd;color:#856404;}
  .btn{display:inline-block;padding:10px 24px;border-radius:4px;
       color:#fff;text-decoration:none;font-weight:bold;margin:4px;}
  .btn-success{background:#198754;}
  .btn-danger{background:#dc3545;}
  .btn-secondary{background:#6c757d;}
  textarea{width:100%;box-sizing:border-box;padding:10px;border:1px solid #ccc;
           border-radius:4px;font-size:14px;resize:vertical;margin:12px 0;}
  form .actions{margin-top:8px;}
</style>
"""

    def _po_label(self, order):
        if not order:
            return 'Purchase Order'
        return html.escape('%s — %s' % (order.name, order.partner_id.name))

    def _render_result(self, page, order=None, approver=None, token=None,
                        reason=None):
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        po_url = '%s/odoo/purchase/%s' % (base_url, order.id) if order else '#'

        if page == 'approved':
            body = """
<div class="card">
  <div class="icon">✅</div>
  <h2 style="color:#198754;">Purchase Order Approved</h2>
  <p>You have successfully approved <strong>%(po)s</strong>.</p>
  <p>The buyer has been notified and may now confirm the order.</p>
  <a href="%(url)s" class="btn btn-success">View Purchase Order</a>
</div>
""" % {'po': self._po_label(order), 'url': po_url}

        elif page == 'reject_form':
            reject_url = '/purchase-approval/%s/reject' % token
            body = """
<div class="card">
  <div class="icon">❌</div>
  <h2 style="color:#dc3545;">Reject Purchase Order</h2>
  <p>You are rejecting <strong>%(po)s</strong>.<br/>
     Please provide a reason so the buyer can address your concerns.</p>
  <form method="POST" action="%(url)s">
    <input type="hidden" name="csrf_token" value="%(csrf)s"/>
    <textarea name="reason" rows="4"
              placeholder="Enter rejection reason..."></textarea>
    <div class="actions">
      <button type="submit" class="btn btn-danger">Confirm Rejection</button>
      <a href="%(po_url)s" class="btn btn-secondary">Cancel</a>
    </div>
  </form>
</div>
""" % {
    'po': self._po_label(order),
    'url': reject_url,
    'csrf': http.request.csrf_token() if hasattr(http.request, 'csrf_token') else '',
    'po_url': po_url,
}

        elif page == 'rejected':
            body = """
<div class="card">
  <div class="icon">🚫</div>
  <h2 style="color:#dc3545;">Purchase Order Rejected</h2>
  <p>You have rejected <strong>%(po)s</strong>.</p>
  <p><strong>Reason:</strong> %(reason)s</p>
  <p>The buyer has been notified.</p>
  <a href="%(url)s" class="btn btn-secondary">View Purchase Order</a>
</div>
""" % {'po': self._po_label(order), 'reason': html.escape(reason or ''), 'url': po_url}

        elif page == 'already_processed':
            body = """
<div class="card">
  <div class="icon">ℹ️</div>
  <h2 style="color:#0d6efd;">Already Processed</h2>
  <p>This approval request for <strong>%(po)s</strong> has already been
     processed or is no longer awaiting your action.</p>
  <a href="%(url)s" class="btn btn-secondary">View Purchase Order</a>
</div>
""" % {'po': self._po_label(order), 'url': po_url}

        elif page == 'error':
            body = """
<div class="card">
  <div class="icon">⚠️</div>
  <h2 style="color:#dc3545;">Action Failed</h2>
  <p>An error occurred while processing your request.</p>
  <p>Please open the purchase order in Odoo for details.</p>
  <a href="%(url)s" class="btn btn-secondary">Open in Odoo</a>
</div>
""" % {'url': po_url}

        else:  # invalid
            body = """
<div class="card">
  <div class="icon">🔒</div>
  <h2 style="color:#6c757d;">Invalid or Expired Link</h2>
  <p>This approval link is no longer valid. The purchase order may have already
     been approved, rejected, or cancelled.</p>
  <p>Please log in to Odoo to check the current status.</p>
  <a href="%(url)s" class="btn btn-secondary">Go to Odoo</a>
</div>
""" % {'url': base_url + '/odoo/purchase'}

        html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Purchase Approval</title>%(style)s</head>
<body>%(body)s</body>
</html>""" % {'style': self._STYLE, 'body': body}

        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )
