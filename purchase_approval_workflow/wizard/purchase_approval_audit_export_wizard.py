# -*- coding: utf-8 -*-
"""Feature 14 — Export Audit Trail as Excel (.xlsx) or PDF."""
import io
import base64
from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseApprovalAuditExportWizard(models.TransientModel):
    _name = 'purchase.approval.audit.export.wizard'
    _description = 'Export Purchase Approval Audit Trail'

    date_from = fields.Date(string='Date From', help='Leave empty to include all dates.')
    date_to = fields.Date(string='Date To', help='Leave empty to include all dates.')
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        help='Filter by a specific PO. Leave empty to export all.',
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        help='Filter to a specific approver.',
    )
    decision = fields.Selection(
        [('approved', 'Approved'), ('rejected', 'Rejected')],
        string='Decision',
        help='Filter by decision outcome.',
    )
    export_format = fields.Selection(
        [('xlsx', 'Excel (.xlsx)'), ('pdf', 'PDF Report')],
        string='Format',
        default='xlsx',
        required=True,
    )
    record_count = fields.Integer(
        string='Matching Records',
        compute='_compute_record_count',
    )

    @api.depends('date_from', 'date_to', 'purchase_order_id', 'approver_id', 'decision')
    def _compute_record_count(self):
        for wizard in self:
            wizard.record_count = len(wizard._get_records())

    def _get_records(self):
        domain = []
        if self.date_from:
            domain.append(('date', '>=', datetime.combine(self.date_from, time.min)))
        if self.date_to:
            domain.append(('date', '<=', datetime.combine(self.date_to, time(23, 59, 59))))
        if self.purchase_order_id:
            domain.append(('purchase_order_id', '=', self.purchase_order_id.id))
        if self.approver_id:
            domain.append(('approver_id', '=', self.approver_id.id))
        if self.decision:
            domain.append(('decision', '=', self.decision))
        return self.env['purchase.approval.history'].search(domain, order='date asc')

    def action_export(self):
        self.ensure_one()
        records = self._get_records()
        if not records:
            raise UserError(_('No records found matching the selected filters.'))
        if self.export_format == 'xlsx':
            return self._export_xlsx(records)
        return self._export_pdf(records)

    def _export_xlsx(self, records):
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_(
                'The "xlsxwriter" Python package is required for Excel export '
                'but is not installed on this server.\n\n'
                'Ask your system administrator to run:\n'
                '    pip install xlsxwriter\n\n'
                'Alternatively, use the PDF export format which has no extra dependencies.'
            ))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Approval Audit Trail')

        # ── Formats ──────────────────────────────────────────────────────────
        hdr = workbook.add_format({
            'bold': True, 'bg_color': '#1F4E79', 'font_color': 'white',
            'border': 1, 'align': 'center', 'valign': 'vcenter', 'font_size': 11,
        })
        cell = workbook.add_format({'border': 1, 'valign': 'top', 'font_size': 10})
        wrap = workbook.add_format({'border': 1, 'valign': 'top', 'text_wrap': True, 'font_size': 10})
        money = workbook.add_format({'border': 1, 'num_format': '#,##0.00', 'font_size': 10})
        approved_fmt = workbook.add_format({
            'border': 1, 'font_color': '#155724', 'bg_color': '#d4edda',
            'bold': True, 'align': 'center', 'font_size': 10,
        })
        rejected_fmt = workbook.add_format({
            'border': 1, 'font_color': '#721c24', 'bg_color': '#f8d7da',
            'bold': True, 'align': 'center', 'font_size': 10,
        })
        total_lbl = workbook.add_format({
            'bold': True, 'bg_color': '#BDD7EE', 'border': 1,
            'font_size': 10, 'align': 'right',
        })
        total_num = workbook.add_format({
            'bold': True, 'bg_color': '#BDD7EE', 'border': 1,
            'num_format': '#,##0.00', 'font_size': 10,
        })
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 14, 'font_color': '#1F4E79',
        })
        subtitle_fmt = workbook.add_format({'font_size': 10, 'italic': True, 'font_color': '#666666'})

        # ── Title block ───────────────────────────────────────────────────────
        sheet.merge_range('A1:I1', 'Purchase Order Approval Audit Trail', title_fmt)
        sheet.write('A2', 'Generated: %s  |  Records: %d' % (
            datetime.now().strftime('%Y-%m-%d %H:%M'), len(records)
        ), subtitle_fmt)
        sheet.set_row(0, 24)

        # ── Column headers (row 3 = index 3) ─────────────────────────────────
        headers = [
            'PO Reference', 'Vendor', 'PO Amount', 'Level',
            'Approver', 'Decision', 'Decision Date', 'Rule', 'Notes / Reason',
        ]
        col_widths = [18, 26, 14, 7, 26, 12, 20, 22, 40]
        sheet.set_row(3, 18)
        for col, (label, width) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, label, hdr)
            sheet.set_column(col, col, width)

        # ── Data rows ─────────────────────────────────────────────────────────
        decision_labels = dict(
            self.env['purchase.approval.history']._fields['decision'].selection
        )
        total_amount = 0.0
        for row_idx, rec in enumerate(records, start=4):
            sheet.write(row_idx, 0, rec.purchase_order_name or '', cell)
            sheet.write(row_idx, 1, rec.partner_id.name or '', cell)
            sheet.write(row_idx, 2, rec.amount_total, money)
            total_amount += rec.amount_total
            sheet.write(row_idx, 3, rec.approval_level, cell)
            sheet.write(row_idx, 4, rec.approver_id.name or '', cell)
            dec_fmt = approved_fmt if rec.decision == 'approved' else rejected_fmt
            sheet.write(row_idx, 5, decision_labels.get(rec.decision, rec.decision), dec_fmt)
            date_str = rec.date.strftime('%Y-%m-%d %H:%M') if rec.date else ''
            sheet.write(row_idx, 6, date_str, cell)
            sheet.write(row_idx, 7, rec.matrix_id.name or '', cell)
            sheet.write(row_idx, 8, rec.notes or '', wrap)

        # ── Totals row ────────────────────────────────────────────────────────
        last_row = 4 + len(records)
        sheet.merge_range(last_row, 0, last_row, 1, 'TOTAL  (%d records)' % len(records), total_lbl)
        sheet.write(last_row, 2, total_amount, total_num)
        for col in range(3, 9):
            sheet.write(last_row, col, '', total_lbl)

        workbook.close()
        xlsx_data = output.getvalue()

        filename = 'PO_Approval_Audit_Trail_%s.xlsx' % fields.Date.today().strftime('%Y%m%d')
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(xlsx_data),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d/%s?download=true' % (attachment.id, filename),
            'target': 'new',
        }

    def _export_pdf(self, records):
        report = self.env.ref('purchase_approval_workflow.action_report_purchase_approval_audit_trail')
        return report.report_action(records)
