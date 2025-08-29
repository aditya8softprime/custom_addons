from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta



class ClinicAppointment(models.Model):
    _name = 'clinic.appointment'
    _description = 'Clinic Appointment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'appointment_date desc, id desc'
    
    name = fields.Char(string='Reference', readonly=True, copy=False, default='New')
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True, tracking=True)
    patient_age = fields.Integer(related='patient_id.age', string='Age', store=True)
    patient_gender = fields.Selection(related='patient_id.gender', string='Gender', store=True)
    patient_phone = fields.Char(related='patient_id.phone', string='Phone', store=True)
    patient_email = fields.Char(related='patient_id.email', string='Email', store=True)
    
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True, tracking=True)
    slot_id = fields.Many2one('clinic.slot', string='Slot', required=True, tracking=True)
    appointment_date = fields.Date(string='Appointment Date', required=True, tracking=True)
    
    # Start and end time are computed from the slot
    start_time = fields.Float(related='slot_id.start_time', string='Start Time', store=True)
    end_time = fields.Float(related='slot_id.end_time', string='End Time', store=True)
    
    consulting_fee = fields.Monetary(string='Consulting Fee', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    
    symptom = fields.Text(string='Symptoms/Problem', tracking=True)

    # Follow-up information
    next_visit_days = fields.Integer(string='Next Visit in Days', tracking=True)
    next_visit_date = fields.Date(string='Next Visit Date', compute='_compute_next_visit_date', store=True)
    
    # Lab tests flag
    is_lab_test_required = fields.Boolean(string='Lab Test Required', tracking=True)
    
    # Related records
    prescription_ids = fields.One2many('clinic.prescription', 'appointment_id', string='Prescriptions')
    lab_test_ids = fields.One2many('clinic.lab.test', 'appointment_id', string='Lab Tests')
    invoice_id = fields.Many2one('account.move', string='Invoice')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('in_consultation', 'In Consultation'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled')
    ], string='Status', default='draft', tracking=True)
    
    cancellation_reason = fields.Text(string='Cancellation Reason')
    checked_in_time = fields.Datetime(string='Checked In Time')
    consultation_start_time = fields.Datetime(string='Consultation Start Time')
    consultation_end_time = fields.Datetime(string='Consultation End Time')
    
    # Reschedule info
    original_appointment_id = fields.Many2one('clinic.appointment', string='Original Appointment')
    rescheduled_to_id = fields.Many2one('clinic.appointment', string='Rescheduled To')
    
    color = fields.Integer(string='Color', compute='_compute_color')
    
    prescription_count = fields.Integer(compute='_compute_counts')
    lab_test_count = fields.Integer(compute='_compute_counts')
    
    @api.depends('state')
    def _compute_color(self):
        """Set color based on state for kanban view"""
        for appointment in self:
            if appointment.state == 'draft':
                appointment.color = 0  # White
            elif appointment.state == 'confirmed':
                appointment.color = 4  # Light Blue
            elif appointment.state == 'checked_in':
                appointment.color = 2  # Green
            elif appointment.state == 'in_consultation':
                appointment.color = 1  # Red
            elif appointment.state == 'completed':
                appointment.color = 10  # Green
            elif appointment.state == 'no_show':
                appointment.color = 3  # Yellow
            elif appointment.state == 'cancelled':
                appointment.color = 1  # Red
            elif appointment.state == 'rescheduled':
                appointment.color = 6  # Purple
            else:
                appointment.color = 0
    
    @api.depends('prescription_ids', 'lab_test_ids')
    def _compute_counts(self):
        for record in self:
            record.prescription_count = len(record.prescription_ids)
            record.lab_test_count = len(record.lab_test_ids)
    
    @api.depends('next_visit_days', 'appointment_date')
    def _compute_next_visit_date(self):
        for appointment in self:
            if appointment.next_visit_days and appointment.appointment_date:
                appointment.next_visit_date = appointment.appointment_date + timedelta(days=appointment.next_visit_days)
            else:
                appointment.next_visit_date = False
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('clinic.appointment') or 'New'
        return super(ClinicAppointment, self).create(vals_list)
    
    def write(self, vals):
        # If state changes to completed, update patient's symptom
        result = super(ClinicAppointment, self).write(vals)
        if vals.get('state') == 'completed':
            for rec in self:
                if rec.patient_id and rec.symptom:
                    rec.patient_id._get_symptoms_from_appointments()
        return result

    @api.onchange('doctor_id', 'appointment_date')
    def _onchange_doctor_appointment_date(self):
        self.slot_id = False  # reset previous selection

        if not self.doctor_id or not self.appointment_date:
            return

        # Determine day of week
        weekday = self.appointment_date.weekday()  # 0 = Monday
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_name = day_names[weekday]

        # Find day record
        day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
        if not day:
            return

        # Check doctor availability
        if day not in self.doctor_id.available_days:
            return {
                'warning': {
                    'title': 'Doctor Not Available',
                    'message': f"Doctor {self.doctor_id.name} is not available on {day_name}"
                }
            }

        # Check holidays
        holidays = self.env['clinic.holiday'].search([
            ('doctor_id', '=', self.doctor_id.id),
            ('state', '=', 'approved'),
            ('from_date', '<=', self.appointment_date),
            ('to_date', '>=', self.appointment_date)
        ])
        if holidays:
            return {
                'warning': {
                    'title': 'Doctor on Leave',
                    'message': f"Doctor {self.doctor_id.name} is on leave on {self.appointment_date.strftime('%Y-%m-%d')}"
                }
            }

        # Set dynamic domain for slot_id
        domain = [
            ('doctor_id', '=', self.doctor_id.id),
            ('day_id', '=', day.id),
            ('status', '=', 'available')
        ]
        return {'domain': {'slot_id': domain}}

    def action_confirm(self):
        """Confirm the appointment"""
        for appointment in self:
            # Check if slot is still available
            if appointment.slot_id.status != 'available' and appointment.state == 'draft':
                raise ValidationError(_("The selected slot is no longer available"))
            
            # Update slot status
            appointment.slot_id.status = 'booked'
            
            # Set consulting fee if not set
            if not appointment.consulting_fee and appointment.doctor_id:
                appointment.consulting_fee = appointment.doctor_id.consultation_fee
            
            appointment.state = 'confirmed'
    
    def action_check_in(self):
        """Mark patient as checked in"""
        self.write({
            'state': 'checked_in',
            'checked_in_time': fields.Datetime.now()
        })
    
    def action_start_consultation(self):
        """Start the consultation"""
        self.write({
            'state': 'in_consultation',
            'consultation_start_time': fields.Datetime.now()
        })
    
    def action_complete(self):
        """Complete the appointment"""
        self.write({
            'state': 'completed',
            'consultation_end_time': fields.Datetime.now()
        })
        
        # Create follow-up appointment if needed
        if self.next_visit_days and self.next_visit_date:
            self._create_followup_appointment()
    
    def action_cancel(self):
        """Cancel the appointment"""
        for appointment in self:
            if appointment.state in ['completed']:
                raise ValidationError(_("Cannot cancel a completed appointment"))
            
            appointment.write({
                'state': 'cancelled',
            })
            
            # Free up the slot
            if appointment.slot_id and appointment.slot_id.status == 'booked':
                appointment.slot_id.status = 'available'
    
    def action_mark_no_show(self):
        """Mark patient as no-show"""
        self.write({'state': 'no_show'})
        
        # Free up the slot
        for appointment in self:
            if appointment.slot_id and appointment.slot_id.status == 'booked':
                appointment.slot_id.status = 'available'
    
    def action_reschedule(self):
        """Open the reschedule wizard"""
        self.ensure_one()
        return {
            'name': _('Reschedule Appointment'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.reschedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_appointment_id': self.id,
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
            }
        }


    
    def action_create_prescription(self):
        """Create a new prescription"""
        self.ensure_one()
        return {
            'name': _('Create Prescription'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.prescription',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
                'default_appointment_id': self.id,
            }
        }
    
    def action_view_prescriptions(self):
        """View prescriptions"""
        self.ensure_one()
        return {
            'name': _('Prescriptions'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.prescription',
            'view_mode': 'list,form',
            'domain': [('appointment_id', '=', self.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
                'default_appointment_id': self.id,
            }
        }
    
    def action_create_lab_test(self):
        """Create a new lab test"""
        self.ensure_one()
        return {
            'name': _('Create Lab Test'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.lab.test',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
                'default_appointment_id': self.id,
            }
        }
    
    def action_view_lab_tests(self):
        """View lab tests"""
        self.ensure_one()
        return {
            'name': _('Lab Tests'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.lab.test',
            'view_mode': 'list,form',
            'domain': [('appointment_id', '=', self.id)],
            'context': {
                'default_patient_id': self.patient_id.id,
                'default_doctor_id': self.doctor_id.id,
                'default_appointment_id': self.id,
            }
        }
    
    def _create_followup_appointment(self):
        """Create a follow-up appointment based on next visit date"""
        self.ensure_one()
        
        # Try to find an available slot on the next visit date
        day_name = self.next_visit_date.strftime('%A')
        day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
        
        if not day or day not in self.doctor_id.available_days:
            # Doctor doesn't work on this da    y, can't create follow-up automatically
            return
        
        # Check if doctor is on leave
        holidays = self.env['clinic.holiday'].search([
            ('doctor_id', '=', self.doctor_id.id),
            ('state', '=', 'approved'),
            ('from_date', '<=', self.next_visit_date),
            ('to_date', '>=', self.next_visit_date)
        ])
        
        if holidays:
            # Doctor is on leave, can't create follow-up automatically
            return
        
        # Find available slot
        available_slot = self.env['clinic.slot'].search([
            ('doctor_id', '=', self.doctor_id.id),
            ('day_id', '=', day.id),
            ('status', '=', 'available')
        ], limit=1)
        
        if not available_slot:
            # No available slots, can't create follow-up automatically

            return
        
        # Create follow-up appointment
        follow_up = self.create({
            'patient_id': self.patient_id.id,
            'doctor_id': self.doctor_id.id,
            'slot_id': available_slot.id,
            'appointment_date': self.next_visit_date,
            'consulting_fee': self.doctor_id.consultation_fee,
            'symptom': self.symptom,
            'state': 'draft',
            'original_appointment_id': self.id,
        })
        
        # Link back to the original appointment
        self.rescheduled_to_id = follow_up.id
        
        # Auto-confirm the follow-up
        follow_up.action_confirm()
        
        return follow_up

    def action_create_invoice(self):
        """Create invoice for consultation fee and prescription medicines"""
        self.ensure_one()

        if self.invoice_id:
            # If invoice already exists, open it
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': self.invoice_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.patient_id.id,
            'invoice_date': fields.Date.context_today(self),
            'ref': f'Appointment: {self.name or ""}',
            'invoice_line_ids': []
        }

        # ------------------------
        # 1. Add consultation fee line
        # ------------------------
        if self.doctor_id.consultation_fee:
            doctor_vals = self.doctor_id.get_consultation_product_vals()
            consultation_line = (0, 0, {
                'product_id': doctor_vals['product'].id,
                'name': doctor_vals['description'],
                'quantity': 1,
                'price_unit': doctor_vals['price_unit'],
                'account_id': doctor_vals['product'].property_account_income_id.id,
            })
            invoice_vals['invoice_line_ids'].append(consultation_line)

        # ------------------------
        # 2. Add prescription medication lines
        # ------------------------
        for prescription in self.prescription_ids:
            for medication in prescription.medication_ids:
                if medication.product_id and medication.quantity > 0:
                    account = medication.product_id.property_account_income_id or \
                              medication.product_id.categ_id.property_account_income_categ_id
                    med_line = (0, 0, {
                        'product_id': medication.product_id.id,
                        'name': f'{medication.product_id.name} - {medication.dosage or ""} - {medication.frequency or ""}',
                        'quantity': medication.quantity,
                        'price_unit': medication.unit_price,
                        'account_id': account.id,
                    })
                    invoice_vals['invoice_line_ids'].append(med_line)

        # ------------------------
        # 3. Validate lines exist
        # ------------------------
        if not invoice_vals['invoice_line_ids']:
            raise ValidationError(_('No items to invoice. Please add consultation fee or prescription medications.'))

        # ------------------------
        # 4. Create invoice
        # ------------------------
        invoice = self.env['account.move'].create(invoice_vals)
        self.invoice_id = invoice.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }
    def action_view_invoice(self):
        """View the created invoice"""
        if not self.invoice_id:
            raise ValidationError(_('No invoice found for this appointment.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _get_consultation_product(self):
        """Get or create consultation fee product"""
        product = self.env['product.product'].search([
            ('name', '=', 'Consultation Fee'),
            ('type', '=', 'service')
        ], limit=1)
        
        if not product:
            product = self.env['product.product'].create({
                'name': 'Consultation Fee',
                'type': 'service',
                'categ_id': self.env.ref('product.product_category_all').id,
                'list_price': 500.0,  # Default price
                'sale_ok': True,
                'purchase_ok': False,
                'detailed_type': 'service',
            })
        
        return product
    
    def _get_patient_partner(self):
        """Get or create partner for patient"""
        partner = self.env['res.partner'].search([
            ('phone', '=', self.patient_id.phone)
        ], limit=1)
        
        if not partner:
            partner = self.env['res.partner'].create({
                'name': self.patient_id.name,
                'phone': self.patient_id.phone,
                'email': self.patient_id.email,
                'is_company': False,
                'customer_rank': 1,
            })
        
        return partner
    
    def _get_income_account(self):
        """Get income account for clinic services"""
        account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        if not account:
            # Fallback to any income account
            account = self.env['account.account'].search([
                ('account_type', '=', 'income')
            ], limit=1)
        return account
