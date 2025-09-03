from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta, datetime
import pytz
import io
import base64
import logging



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
    
    service_id = fields.Many2one('clinic.service', string='Service', required=True, tracking=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True, tracking=True)
    slot_id = fields.Many2one('clinic.slot', string='Slot', required=True, tracking=True,)
    slots = fields.Many2many('clinic.slot', string='Slots')

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
    medicine_image = fields.Binary(string='Medicine / Prescription Image',attachment=True)
    medicine_image_filename = fields.Char(string='Medicine Image Filename')
    medicine_pdf = fields.Binary(string='Medicine / Prescription PDF', attachment=True)
    medicine_pdf_filename = fields.Char(string='Medicine PDF Filename')
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
    
    @api.depends('lab_test_ids')
    def _compute_counts(self):
        for record in self:
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

    @api.onchange('service_id')
    def _onchange_service_id(self):
        """Filter doctors based on selected service"""
        self.doctor_id = False  # reset doctor selection
        self.slot_id = False  # reset slot selection
        
        if not self.service_id:
            return {'domain': {'doctor_id': []}}
        
        # Find doctors who have this service in their specializations
        doctors = self.env['clinic.doctor'].search([
            ('specialization_ids', 'in', self.service_id.id),
            ('active', '=', True)
        ])
        
        domain = [('id', 'in', doctors.ids)]
        return {'domain': {'doctor_id': domain}}

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
        slots = self.env['clinic.slot'].search([
            ('doctor_id', '=', self.doctor_id.id),
            ('day_id', '=', day.id),
            ('status', '=', 'available')
        ])
        self.slots = slots
        return {'domain': {'slot_id': [('id', 'in', slots.ids)]}}



    def action_confirm(self):
        """Confirm the appointment"""
        for appointment in self:
            # Check if slot is still available
            if appointment.slot_id.status != 'available' and appointment.state == 'draft':
                raise ValidationError(_("The selected slot is no longer available"))
            
            # Update slot status
            appointment.slot_id.sudo().status = 'booked'
            
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

    def reset_to_in_consultation(self):
        """Reset the appointment state to in consultation"""
        self.write({
            'state': 'in_consultation',
            'consultation_start_time': fields.Datetime.now()
        })

    def action_complete(self):
        """Complete the appointment: set state, optionally create follow-up, generate PDF from medicine_image,
        attach it and send completion email to patient."""
        for appointment in self:
            appointment.write({
                'state': 'completed',
                'consultation_end_time': fields.Datetime.now()
            })

            # Create follow-up appointment if needed
            if appointment.next_visit_days and appointment.next_visit_date:
                appointment._create_followup_appointment()

            # Prepare attachments list
            attachment_ids = []

            # If a handwritten medicine image exists, try to convert it to PDF
            if appointment.medicine_image:
                try:
                    image_b = base64.b64decode(appointment.medicine_image)
                    pdf_bytes = None

                    # Try img2pdf first (fast, preserves size)
                    try:
                        import img2pdf
                        pdf_bytes = img2pdf.convert(image_b)
                    except Exception:
                        # Fall back to Pillow
                        try:
                            from PIL import Image
                            img_buf = io.BytesIO(image_b)
                            img = Image.open(img_buf)
                            # Ensure RGB for PDF
                            if img.mode in ('RGBA', 'LA'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                background.paste(img, mask=img.split()[-1])
                                img = background
                            else:
                                img = img.convert('RGB')
                            out_buf = io.BytesIO()
                            img.save(out_buf, format='PDF')
                            pdf_bytes = out_buf.getvalue()
                        except Exception:
                            pdf_bytes = None

                    if pdf_bytes:
                        # Save PDF on the appointment record and create an attachment linked to it
                        pdf_b64 = base64.b64encode(pdf_bytes).decode()
                        pdf_name = f"Prescription_{appointment.name or ''}.pdf"
                        if appointment.medicine_image_filename:
                            # Replace extension with .pdf
                            base_name = appointment.medicine_image_filename.rsplit('.', 1)[0]
                            pdf_name = f"{base_name}.pdf"

                        # store on record
                        try:
                            appointment.medicine_pdf = pdf_b64
                            appointment.medicine_pdf_filename = pdf_name
                        except Exception:
                            # non-fatal if writing fails
                            logging.getLogger(__name__).exception('Failed to write medicine_pdf on appointment %s', appointment.id)

                        # create ir.attachment so it appears in object.attachment_ids for the template
                        attachment = self.env['ir.attachment'].create({
                            'name': pdf_name,
                            'type': 'binary',
                            'datas': pdf_b64,
                            'res_model': 'clinic.appointment',
                            'res_id': appointment.id,
                            'mimetype': 'application/pdf',
                        })
                        attachment_ids.append(attachment.id)
                    else:
                        # Fallback: attach original image (and keep existing medicine_image on record)
                        img_name = appointment.medicine_image_filename or f"Prescription_{appointment.name or ''}.png"
                        try:
                            attachment = self.env['ir.attachment'].create({
                                'name': img_name,
                                'type': 'binary',
                                'datas': appointment.medicine_image,
                                'res_model': 'clinic.appointment',
                                'res_id': appointment.id,
                                'mimetype': 'image/png',
                            })
                            attachment_ids.append(attachment.id)
                        except Exception:
                            logging.getLogger(__name__).exception('Failed to attach original image for appointment %s', appointment.id)

                except Exception:
                    logging.getLogger(__name__).exception('Failed to convert/attach medicine_image for appointment %s', appointment.id)

            # Send completion email with attachments (if patient has email)
            try:
                if appointment.patient_id and appointment.patient_id.email:
                    template = self.env.ref('clinic_management.email_template_appointment_complete', False)
                    if template:
                        # Send email with explicit attachment ids to ensure they are included
                        email_values = {
                            'attachment_ids': [(4, att_id) for att_id in attachment_ids] if attachment_ids else False
                        }
                        template.attachment_ids = [(6, 0, attachment_ids)]
                        template.send_mail(appointment.id, force_send=True, email_values=email_values)
            except Exception:
                logging.getLogger(__name__).exception('Failed to send completion email for appointment %s', appointment.id)
    
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
            # Previously opened the prescription form; removed as prescription model deprecated
            'res_model': 'clinic.appointment',
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
            # Prescription model removed; show appointment form instead as placeholder
            'res_model': 'clinic.appointment',
            'view_mode': 'form',
            'res_id': self.id,
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

        # Only receptionist and admins are allowed to create invoices from appointments
        allowed_groups = [self.env.ref('clinic_management.group_clinic_receptionist').id, self.env.ref('clinic_management.group_clinic_admin').id]
        user_group_ids = self.env.user.groups_id.ids
        if not (set(allowed_groups) & set(user_group_ids)) and not self.env.user.has_group('base.group_system'):
            raise ValidationError(_('You do not have permission to create invoices.'))

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
        consultation_product = self.env['product.product'].search([
            ('name', '=', 'Consultation'),
            ('type', '=', 'service')
        ], limit=1)
        if not consultation_product:
            consultation_product = self._get_consultation_product()
        if self.consulting_fee:
            consultation_line = (0, 0, {
                'product_id': consultation_product.id,
                'name': self.name,
                'quantity': 1,
                'price_unit': self.consulting_fee,
                # 'account_id': consultation_product.property_account_income_id.id,
            })
            invoice_vals['invoice_line_ids'].append(consultation_line)

    # ------------------------
    # 2. (Deprecated) Prescription medication lines were stored on prescription model.
    # If you migrate medications to appointment, add them here.
    # ------------------------

        # ------------------------
        # 3. Validate lines exist
        # ------------------------
        if not invoice_vals['invoice_line_ids']:
            raise ValidationError(_('No items to invoice. Please add consultation fee or prescription medications.'))

        # ------------------------
        # 4. Create invoice
        # ------------------------
        invoice = self.env['account.move'].create(invoice_vals)
        invoice.action_post()
        self.invoice_id = invoice.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'context': {'create': False, 'edit': False},
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

    @api.model
    def get_appointment_dashboard_data(self, doctor_id=None, time_filter=None):
        """Return data for the appointment dashboard tiles"""
        company_id = self.env.company.id
        
        # Build dynamic domain for appointments
        domain = [('company_id', '=', company_id)]
        if doctor_id:
            domain.append(('doctor_id', '=', int(doctor_id)))
            
        # Apply time filter
        if time_filter:
            user_tz = self.env.user.tz or 'UTC'
            tz = pytz.timezone(user_tz)
            now = datetime.now(tz)
            
            if time_filter == 'today':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59)
            elif time_filter == 'week':
                start_date = now - timedelta(days=now.weekday())
                start_date = start_date.replace(hour=0, minute=0, second=0)
                end_date = start_date + timedelta(days=6, hours=23, minutes=59)
            elif time_filter == 'month':
                start_date = now.replace(day=1, hour=0, minute=0, second=0)
                next_month = (start_date + timedelta(days=31)).replace(day=1)
                end_date = next_month - timedelta(seconds=1)
            elif time_filter == 'year':
                start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0)
                end_date = now.replace(month=12, day=31, hour=23, minute=59)
            
            if start_date and end_date:
                utc_tz = pytz.UTC
                start_date_utc = start_date.astimezone(utc_tz)
                end_date_utc = end_date.astimezone(utc_tz)
                domain.append(('appointment_date', '>=', start_date_utc.date()))
                domain.append(('appointment_date', '<=', end_date_utc.date()))
        
        # Fetch appointments
        appointments = self.env['clinic.appointment'].search(domain)
        
        # Filter by state
        draft = appointments.filtered(lambda r: r.state == 'draft')
        confirmed = appointments.filtered(lambda r: r.state == 'confirmed')
        checked_in = appointments.filtered(lambda r: r.state == 'checked_in')
        in_consultation = appointments.filtered(lambda r: r.state == 'in_consultation')
        completed = appointments.filtered(lambda r: r.state == 'completed')
        no_show = appointments.filtered(lambda r: r.state == 'no_show')
        cancelled = appointments.filtered(lambda r: r.state == 'cancelled')
        rescheduled = appointments.filtered(lambda r: r.state == 'rescheduled')
        
        # Calculate revenue from completed appointments
        total_revenue = sum(completed.mapped('consulting_fee'))

        # Count lab tests (prescription model removed; handwritten image stored on appointment)
        total_lab_tests = sum(len(a.lab_test_ids) for a in appointments)

        return {
            'total_appointments': len(appointments),
            'total_draft': len(draft),
            'total_confirmed': len(confirmed),
            'total_checked_in': len(checked_in),
            'total_in_consultation': len(in_consultation),
            'total_completed': len(completed),
            'total_no_show': len(no_show),
            'total_cancelled': len(cancelled),
            'total_rescheduled': len(rescheduled),
            'total_revenue': total_revenue,
            'total_lab_tests': total_lab_tests,
        }
    
    @api.model
    def get_appointment_list_data(self, doctor_id=None, time_filter=None, state=None, offset=0, limit=15):
        """Fetch appointment data for the dashboard table"""
        company_id = self.env.company.id
        
        # Build domain
        domain = [('company_id', '=', company_id)]
        if doctor_id:
            domain.append(('doctor_id', '=', int(doctor_id)))
        if state:
            domain.append(('state', '=', state))
            
        # Apply time filter
        if time_filter and time_filter != 'till_now':
            user_tz = self.env.user.tz or 'UTC'
            tz = pytz.timezone(user_tz)
            now = datetime.now(tz)
            
            if time_filter == 'today':
                start_date = now.replace(hour=0, minute=0, second=0)
                end_date = now.replace(hour=23, minute=59, second=59)
            elif time_filter == 'week':
                start_date = now - timedelta(days=now.weekday())
                start_date = start_date.replace(hour=0, minute=0, second=0)
                end_date = start_date + timedelta(days=6, hours=23, minutes=59)
            elif time_filter == 'month':
                start_date = now.replace(day=1, hour=0, minute=0, second=0)
                next_month = (start_date + timedelta(days=31)).replace(day=1)
                end_date = next_month - timedelta(seconds=1)
            elif time_filter == 'year':
                start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0)
                end_date = now.replace(month=12, day=31, hour=23, minute=59)
                
            if start_date and end_date:
                utc_tz = pytz.UTC
                start_date_utc = start_date.astimezone(utc_tz)
                end_date_utc = end_date.astimezone(utc_tz)
                domain.append(('appointment_date', '>=', start_date_utc.date()))
                domain.append(('appointment_date', '<=', end_date_utc.date()))
        
        # Get total count
        total_records = self.env['clinic.appointment'].search_count(domain)
        
        # Fetch records
        fields = ['id', 'name', 'patient_id', 'doctor_id', 'appointment_date', 'start_time', 'end_time', 'state', 'consulting_fee']
        appointments = self.env['clinic.appointment'].search_read(
            domain, fields, offset=offset, limit=limit, order='appointment_date desc'
        )
        
        # Process records for display
        appointment_records = [{
            'id': appointment['id'],
            'name': appointment['name'],
            'patient_name': appointment['patient_id'][1] if appointment['patient_id'] else '-',
            'doctor_name': appointment['doctor_id'][1] if appointment['doctor_id'] else '-',
            'appointment_date': appointment['appointment_date'].strftime('%d/%m/%Y') if appointment['appointment_date'] else '-',
            'time_slot': f"{self._float_to_time(appointment['start_time'])} - {self._float_to_time(appointment['end_time'])}",
            'state': appointment['state'],
            'consulting_fee': appointment['consulting_fee'],
        } for appointment in appointments]
        
        return {
            'total_records': total_records,
            'records': appointment_records,
        }
    
    @api.model
    def _float_to_time(self, float_time):
        """Convert float time to HH:MM format"""
        hours = int(float_time)
        minutes = int((float_time - hours) * 60)
        return f"{hours:02d}:{minutes:02d}"
