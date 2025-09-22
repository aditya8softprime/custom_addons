from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClinicPaymentWizard(models.TransientModel):
    _name = 'clinic.payment.wizard'
    _description = 'Clinic Payment Wizard'

    appointment_id = fields.Many2one('clinic.appointment', string='Appointment', required=True)
    patient_id = fields.Many2one(related='appointment_id.patient_id', string='Patient', readonly=True)
    amount = fields.Float(string='Amount', required=True)
    payment_method_id = fields.Many2one(
        'account.journal', 
        string='Payment Method', 
        required=True,
        domain=[('type', 'in', ['cash', 'bank'])]
    )
    communication = fields.Char(string='Memo', default=lambda self: self._default_communication())
    payment_date = fields.Date(string='Payment Date', default=fields.Date.context_today, required=True)

    def _default_communication(self):
        """Default payment communication"""
        if self.env.context.get('default_appointment_id'):
            appointment = self.env['clinic.appointment'].browse(self.env.context['default_appointment_id'])
            return f"Payment for appointment {appointment.name}"
        return "Appointment Payment"

    @api.onchange('appointment_id')
    def _onchange_appointment_id(self):
        """Update amount when appointment changes"""
        if self.appointment_id:
            self.amount = self.appointment_id.consulting_fee
            self.communication = f"Payment for appointment {self.appointment_id.name}"

    def action_process_payment(self):
        """Process the payment and create account.payment record"""
        self.ensure_one()
        
        if not self.amount or self.amount <= 0:
            raise ValidationError(_('Payment amount must be greater than zero.'))

        # Ensure invoice exists
        if not self.appointment_id.invoice_id:
            self.appointment_id.action_create_invoice()

        invoice = self.appointment_id.invoice_id
        
        # Create payment
        payment_vals = {
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.appointment_id.patient_id.id,
            'amount': self.amount,
            'journal_id': self.payment_method_id.id,
            'date': self.payment_date,
            'invoice_ids': [(6, 0, [invoice.id])],  # FIXED: Pass list of IDs
            'payment_method_line_id': self._get_payment_method_line(),
        }

        payment = self.env['account.payment'].create(payment_vals)
        
        # Post the payment
        payment.action_post()

        # Update appointment with payment info
        self.appointment_id.write({
            'payment_id': payment.id,
            'payment_date': fields.Datetime.now(),
            'payment_method_id': self.payment_method_id.id,
            'state': 'paid'
        })

        # Reconcile payment with invoice
        if invoice.state == 'posted':
            self._reconcile_payment_with_invoice(payment, invoice)
    

    def _get_payment_method_line(self):
        """Get the appropriate payment method line for the journal"""
        payment_method_line = self.payment_method_id.inbound_payment_method_line_ids.filtered(
            lambda l: l.payment_method_id.code in ['manual', 'batch_payment']
        )[:1]
        
        if not payment_method_line:
            payment_method_line = self.payment_method_id.inbound_payment_method_line_ids[:1]
            
        return payment_method_line.id if payment_method_line else False

    def _reconcile_payment_with_invoice(self, payment, invoice):
        """Reconcile payment with invoice"""
        try:
            # Use Odoo's standard reconciliation approach
            # Get the receivable account from the invoice
            receivable_account = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable'
            ).account_id
            
            if receivable_account:
                # Get the payment move line for the receivable account
                payment_line = payment.move_id.line_ids.filtered(
                    lambda line: line.account_id == receivable_account
                )
                
                # Get the invoice move line for the receivable account
                invoice_line = invoice.line_ids.filtered(
                    lambda line: line.account_id == receivable_account
                )
                
                if payment_line and invoice_line:
                    # Reconcile the lines
                    (payment_line + invoice_line).reconcile()
                
        except Exception as e:
            # Log error but don't fail the payment process
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning("Failed to reconcile payment with invoice: %s", str(e))
            
            # Try alternative reconciliation method
            try:
                # Use Odoo's built-in method for assigning payments to invoices
                invoice.js_assign_outstanding_line(payment.id)
            except Exception as fallback_error:
                _logger.error("Fallback reconciliation also failed: %s", str(fallback_error))

    def action_mark_paid_only(self):
        """Mark as paid without creating payment record (for external payments)"""
        self.ensure_one()
        
        if self.appointment_id.appointment_type == 'walkin':
            # For walk-in appointments, move to waiting state
            self.appointment_id.write({
                'state': 'waiting',
                'payment_date': fields.Datetime.now(),
                'payment_method_id': self.payment_method_id.id,
            })
            message = _('Appointment has been marked as paid and moved to waiting queue.')
        else:
            # For scheduled appointments, move to paid state
            self.appointment_id.write({
                'state': 'paid',
                'payment_date': fields.Datetime.now(),
                'payment_method_id': self.payment_method_id.id,
            })
            message = _('Appointment has been marked as paid.')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Marked as Paid'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }