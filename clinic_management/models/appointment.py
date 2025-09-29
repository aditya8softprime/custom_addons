from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta, datetime
import pytz
import io
import base64
import logging

_logger = logging.getLogger(__name__)



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
    
    # Appointment Type
    appointment_type = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('walkin', 'Walk-in')
    ], string='Appointment Type', default='scheduled', required=True, tracking=True)
    
    # Slot for scheduled appointments only
    slot_id = fields.Many2one('clinic.slot', string='Slot', tracking=True)
    slots = fields.Many2many('clinic.slot', string='Slots')
    
    # Queue system for walk-in appointments
    queue_number = fields.Char(string='Queue Number', readonly=True, copy=False)
    queue_position = fields.Integer(string='Position in Queue', compute='_compute_queue_position', store=True)

    appointment_date = fields.Date(string='Appointment Date', required=True, tracking=True)
    
    # Start and end time are computed from the slot (backward compatibility)
    start_time = fields.Float(related='slot_id.start_time_float', string='Start Time', store=True)
    end_time = fields.Float(related='slot_id.end_time_float', string='End Time', store=True)
    
    # New string time fields from slot (new structure)
    start_time_str = fields.Char(related='slot_id.start_time', string='Start Time (String)', store=True)
    end_time_str = fields.Char(related='slot_id.end_time', string='End Time (String)', store=True)
    
    consulting_fee = fields.Monetary(string='Consulting Fee', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    
    # Company fields removed as we now fetch directly in JavaScript
    # Related company fields removed - now fetched directly via RPC
    
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
    
    # Lab test lines (simplified approach)y
    lab_test_line_ids = fields.One2many('appointment.lab.line', 'appointment_id', string='Lab Test Lines')
    invoice_id = fields.Many2one('account.move', string='Invoice')
    
    # Payment information
    payment_id = fields.Many2one('account.payment', string='Payment')
    payment_date = fields.Datetime(string='Payment Date')
    payment_method_id = fields.Many2one('account.journal', string='Payment Method')
    
    state = fields.Selection([
        ('draft', 'New'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('waiting', 'Waiting'),
        ('patient_in', 'Patient In'),
        ('in_consultation', 'In Consultation'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
        ('cancelled', 'Cancelled'),
        ('rescheduled', 'Rescheduled')
    ], string='Status', default='draft', tracking=True)
    
    cancellation_reason = fields.Text(string='Cancellation Reason')
    patient_in_time = fields.Datetime(string='Patient In Time')
    consultation_start_time = fields.Datetime(string='Consultation Start Time')
    consultation_end_time = fields.Datetime(string='Consultation End Time')
    
    # Reschedule info
    original_appointment_id = fields.Many2one('clinic.appointment', string='Original Appointment')
    rescheduled_to_id = fields.Many2one('clinic.appointment', string='Rescheduled To')
    
    color = fields.Integer(string='Color', compute='_compute_color')
    
    lab_test_count = fields.Integer(compute='_compute_counts')
    
    # Previous appointments chain count
    previous_appointments_count = fields.Integer(string='Previous Appointments Count', compute='_compute_previous_appointments_count')
    
    # Fields for next visit follow-up
    next_visit_slot_available = fields.Boolean(string='Next Visit Slot Available', 
                                               compute='_compute_next_visit_slot_available')
    show_reschedule_button = fields.Boolean(string='Show Reschedule Button',
                                           compute='_compute_show_reschedule_button')
    next_visit_status = fields.Char(string='Next Visit Status', compute='_compute_next_visit_status')
    @api.depends('next_visit_date', 'doctor_id')
    def _compute_next_visit_slot_available(self):
        """Check if slot is available on next visit date"""
        for appointment in self:
            appointment.next_visit_slot_available = False
            if appointment.next_visit_date and appointment.doctor_id:
                # Check if next visit date has available slots
                day_name = appointment.next_visit_date.strftime('%A')
                day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
                
                if day and day in appointment.doctor_id.available_days:
                    # Check if doctor is not on leave
                    holidays = self.env['clinic.holiday'].search([
                        ('doctor_id', '=', appointment.doctor_id.id),
                        ('state', '=', 'approved'),
                        ('from_date', '<=', appointment.next_visit_date),
                        ('to_date', '>=', appointment.next_visit_date)
                    ])
                    
                    if not holidays:
                        # Check available slots
                        available_slots = self.env['clinic.slot'].search([
                            ('doctor_id', '=', appointment.doctor_id.id),
                            ('day_id', '=', day.id),
                            ('is_blocked', '=', False)
                        ])
                        appointment.next_visit_slot_available = bool(available_slots)
    
    @api.depends('next_visit_date', 'next_visit_slot_available', 'state')
    def _compute_show_reschedule_button(self):
        """Show reschedule button only in completed state when next visit date is set and slots are available"""
        for appointment in self:
            appointment.show_reschedule_button = (
                appointment.next_visit_date and 
                appointment.next_visit_slot_available and 
                appointment.state == 'completed'
            )
    
    @api.depends('next_visit_date', 'next_visit_slot_available', 'doctor_id')
    def _compute_next_visit_status(self):
        """Compute status message for next visit"""
        for appointment in self:
            if not appointment.next_visit_date:
                appointment.next_visit_status = "No next visit scheduled"
            elif appointment.next_visit_slot_available:
                appointment.next_visit_status = f"Slots available on {appointment.next_visit_date.strftime('%Y-%m-%d')}"
            else:
                appointment.next_visit_status = f"No slots available on {appointment.next_visit_date.strftime('%Y-%m-%d')}"
    
    @api.depends('original_appointment_id')
    def _compute_previous_appointments_count(self):
        """Compute count of previous appointments in the chain"""
        for appointment in self:
            count = 0
            if appointment.original_appointment_id:
                # Find the root appointment and count all appointments in the chain
                root_appointment = appointment._get_root_appointment()
                chain_appointments = appointment._get_appointment_chain(root_appointment)
                # Count only previous appointments (excluding current)
                count = len(chain_appointments) - 1
            appointment.previous_appointments_count = count
    
    @api.depends('state')
    def _compute_color(self):
        """Set color based on state for kanban view"""
        for appointment in self:
            if appointment.state == 'draft':
                appointment.color = 0  # White
            elif appointment.state == 'confirmed':
                appointment.color = 4  # Light Blue
            elif appointment.state == 'waiting':
                appointment.color = 5  # Yellow/Orange
            elif appointment.state == 'paid':
                appointment.color = 9  # Light Green
            elif appointment.state == 'patient_in':
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
    
    @api.depends('lab_test_line_ids')
    def _compute_counts(self):
        for record in self:
            record.lab_test_count = len(record.lab_test_line_ids)
    
    @api.depends('next_visit_days', 'appointment_date')
    def _compute_next_visit_date(self):
        for appointment in self:
            if appointment.next_visit_days and appointment.next_visit_days > 0 and appointment.appointment_date:
                appointment.next_visit_date = appointment.appointment_date + timedelta(days=appointment.next_visit_days)
            else:
                appointment.next_visit_date = False
    
    @api.depends('queue_number', 'doctor_id', 'appointment_date', 'state')
    def _compute_queue_position(self):
        """Compute position in queue for walk-in appointments"""
        for appointment in self:
            if appointment.appointment_type == 'walkin' and appointment.queue_number and appointment.state == 'waiting':
                # Get all waiting walk-in appointments for the same doctor and date
                waiting_appointments = self.search([
                    ('doctor_id', '=', appointment.doctor_id.id),
                    ('appointment_date', '=', appointment.appointment_date),
                    ('appointment_type', '=', 'walkin'),
                    ('state', '=', 'waiting'),
                    ('queue_number', '!=', False)
                ], order='queue_number')
                
                position = 1
                for idx, app in enumerate(waiting_appointments):
                    if app.id == appointment.id:
                        position = idx + 1
                        break
                appointment.queue_position = position
            else:
                appointment.queue_position = 0
    
    def _get_root_appointment(self):
        """Get the root appointment of the chain"""
        current = self
        while current.original_appointment_id:
            current = current.original_appointment_id
        return current
    
    def _get_appointment_chain(self, root_appointment):
        """Get all appointments in the chain starting from root"""
        chain = [root_appointment]
        current = root_appointment
        while current.rescheduled_to_id:
            chain.append(current.rescheduled_to_id)
            current = current.rescheduled_to_id
        return chain
    
    def action_view_previous_appointments(self):
        """View all previous appointments in the chain"""
        self.ensure_one()
        if not self.original_appointment_id:
            return {'type': 'ir.actions.act_window_close'}
        
        root_appointment = self._get_root_appointment()
        chain_appointments = self._get_appointment_chain(root_appointment)
        # Get all previous appointments (excluding current)
        previous_appointment_ids = [app.id for app in chain_appointments if app.id != self.id]
        
        return {
            'name': _('Previous Appointments'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.appointment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', previous_appointment_ids)],
            'context': {'default_patient_id': self.patient_id.id},
        }
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Generate sequence number if name is 'New' or not provided
            if not vals.get('name') or vals.get('name', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code('clinic.appointment')
                if sequence:
                    vals['name'] = sequence
                else:
                    # Fallback if sequence is not found
                    vals['name'] = f"APT{self.env['clinic.appointment'].search_count([]) + 1:05d}"
            
            # Set today's date for walk-in appointments if not provided
            if vals.get('appointment_type') == 'walkin' and not vals.get('appointment_date'):
                vals['appointment_date'] = fields.Date.context_today(self)
            
            # Set consulting fee if not provided and doctor is specified
            if not vals.get('consulting_fee') and vals.get('doctor_id'):
                doctor = self.env['clinic.doctor'].browse(vals['doctor_id'])
                if doctor.consultation_fee:
                    vals['consulting_fee'] = doctor.consultation_fee
            # Preload doctor's prescription template into appointment image if not provided
            if vals.get('doctor_id') and not vals.get('medicine_image'):
                doctor = self.env['clinic.doctor'].browse(vals['doctor_id'])
                if doctor and doctor.prescription_template_image:
                    vals['medicine_image'] = doctor.prescription_template_image
                    vals['medicine_image_filename'] = doctor.prescription_template_filename or f"Prescription_Template_{doctor.name}.png"
        
        appointments = super(ClinicAppointment, self).create(vals_list)
        
        # Handle walk-in appointments after creation
        for appointment in appointments:
            if appointment.appointment_type == 'walkin':
                # Generate queue number for walk-in appointments
                appointment._generate_queue_number()
                
        return appointments
    
    def write(self, vals):
        # If state changes to completed, update patient's symptom
        result = super(ClinicAppointment, self).write(vals)
        if vals.get('state') == 'completed':
            for rec in self:
                if rec.patient_id and rec.symptom:
                    rec.patient_id._get_symptoms_from_appointments()
        return result

    @api.onchange('next_visit_days', 'appointment_date', 'doctor_id')
    def _onchange_next_visit_days(self):
        """Validate next visit slot availability when next_visit_days is set"""
        if self.next_visit_days and self.next_visit_days > 0 and self.appointment_date and self.doctor_id:
            next_date = self.appointment_date + timedelta(days=self.next_visit_days)
            
            # Check if next visit date has available slots
            day_name = next_date.strftime('%A')
            day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
            
            if not day or day not in self.doctor_id.available_days:
                return {
                    'warning': {
                        'title': 'Doctor Not Available',
                        'message': f"Doctor {self.doctor_id.name} is not available on {day_name} ({next_date.strftime('%Y-%m-%d')}). Please choose different days for next visit."
                    }
                }
            
            # Check if doctor is on leave
            holidays = self.env['clinic.holiday'].search([
                ('doctor_id', '=', self.doctor_id.id),
                ('state', '=', 'approved'),
                ('from_date', '<=', next_date),
                ('to_date', '>=', next_date)
            ])
            
            if holidays:
                return {
                    'warning': {
                        'title': 'Doctor on Leave',
                        'message': f"Doctor {self.doctor_id.name} is on leave on {next_date.strftime('%Y-%m-%d')}. Please choose different days for next visit."
                    }
                }
            
            # Check available slots
            available_slots = self.env['clinic.slot'].search([
                ('doctor_id', '=', self.doctor_id.id),
                ('day_id', '=', day.id),
                ('is_blocked', '=', False)
            ])
            
            if not available_slots:
                return {
                    'warning': {
                        'title': 'No Available Slots',
                        'message': f"No available slots for Dr. {self.doctor_id.name} on {next_date.strftime('%Y-%m-%d')}. Please choose different days for next visit."
                    }
                }

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

    @api.onchange('doctor_id')
    def _onchange_doctor_id(self):
        """Set consulting fee and validate if appointment date is already selected"""
        if self.doctor_id:
            # Set consulting fee if not already set
            if not self.consulting_fee:
                self.consulting_fee = self.doctor_id.consultation_fee

            # Auto-load doctor's prescription template as base image for canvas
            if (self.state in (False, 'draft')) and not self.medicine_image and self.doctor_id.prescription_template_image:
                # Only set if not already drawn or always refresh template on doctor change in draft
                # Here we choose to refresh to ensure correct template per doctor
                self.medicine_image = self.doctor_id.prescription_template_image
                self.medicine_image_filename = (
                    self.doctor_id.prescription_template_filename
                    or f"Prescription_Template_{self.doctor_id.name}.png"
                )
            
            # If appointment date is already selected, validate availability
            if self.appointment_date:
                self._validate_doctor_availability()
        return {}
    
    def _validate_doctor_availability(self):
        """Helper method to validate doctor availability on selected date"""
        if not self.doctor_id or not self.appointment_date:
            return {}
        
        # Determine day of week
        weekday = self.appointment_date.weekday()  # 0 = Monday
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_name = day_names[weekday]

        # Find day record
        day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
        if not day:
            raise ValidationError(f"No day configuration found for {day_name}.")


        # Check doctor availability
        if day not in self.doctor_id.available_days:
            raise ValidationError(
                f"Doctor {self.doctor_id.name} is not available on {day_name}. "
                f"Please select a different date or doctor."
            )

        # Check if doctor is on leave
        holidays = self.env['clinic.holiday'].search([
            ('doctor_id', '=', self.doctor_id.id),
            ('state', '=', 'approved'),
            ('from_date', '<=', self.appointment_date),
            ('to_date', '>=', self.appointment_date)
        ])
        if holidays:
           raise ValidationError(
            f"Doctor {self.doctor_id.name} is on leave on {self.appointment_date}. "
            f"Please select a different date or doctor."
            )

        return {}  # No warnings, doctor is available
 
    
    @api.onchange('appointment_type')
    def _onchange_appointment_type(self):
        """Handle appointment type change logic"""
        if self.appointment_type == 'walkin':
            # Clear slot for walk-in appointments and set today's date

            if self.doctor_id:
                self._validate_doctor_availability()
                
            self.slot_id = False
            self.slots = False
            self.appointment_date = fields.Date.context_today(self)
            
            # If doctor is already selected, validate availability for today
           
        elif self.appointment_type == 'scheduled':
            # Clear queue number for scheduled appointments
            self.queue_number = False
        
        return {}

    @api.onchange('doctor_id', 'appointment_date')
    def _onchange_doctor_appointment_date(self):
        self.slot_id = False  # reset previous selection

        if not self.doctor_id or not self.appointment_date:
            return {}
        
        # First validate doctor availability (applies to both scheduled and walk-in)
        availability_warning = self._validate_doctor_availability()
        if availability_warning.get('warning'):
            return availability_warning
        
    # For scheduled appointments, also handle slot availability
        if self.appointment_type == 'scheduled':
            # Determine day of week
            weekday = self.appointment_date.weekday()  # 0 = Monday
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_name = day_names[weekday]

            # Find day record
            day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
            if day:
                slots = self.env['clinic.slot'].search([
                    ('doctor_id', '=', self.doctor_id.id),
                    ('day_id', '=', day.id),
                    ('is_blocked', '=', False)
                ])
                self.slots = slots
                return {'domain': {'slot_id': [('id', 'in', slots.ids)]}}
        
        # For walk-in appointments, no slot validation needed but availability is confirmed
        return {}
        return True



    def action_confirm(self):
        """Confirm the appointment"""
        for appointment in self:
            # For scheduled appointments, validate slot availability
            if appointment.appointment_type == 'scheduled':
                if appointment.slot_id:
                    # slot template must not be blocked
                    if appointment.slot_id.is_blocked and appointment.state == 'draft':
                        raise ValidationError(_("The selected slot is no longer available"))
                    # prevent double-booking: same doctor, date, and slot in active states
                    conflict = self.search_count([
                        ('doctor_id', '=', appointment.doctor_id.id),
                        ('appointment_date', '=', appointment.appointment_date),
                        ('slot_id', '=', appointment.slot_id.id),
                        ('state', 'not in', ['cancelled', 'no_show', 'rescheduled']),
                        ('id', '!=', appointment.id)
                    ])
                    if conflict:
                        raise ValidationError(_("This slot is already booked for the selected date"))
            
            # For walk-in appointments, generate queue number if not present
            elif appointment.appointment_type == 'walkin':
                if not appointment.queue_number:
                    appointment._generate_queue_number()
            
            # Set consulting fee if not set
            if not appointment.consulting_fee and appointment.doctor_id:
                appointment.consulting_fee = appointment.doctor_id.consultation_fee
            
            appointment.state = 'confirmed'
    
    def action_pay(self):
        """Open payment wizard"""
        self.ensure_one()
        return {
            'name': _('Process Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_appointment_id': self.id,
                'default_amount': self.consulting_fee,
            }
        }
    
    def action_mark_paid(self):
        """Mark appointment as paid"""
        self.ensure_one()
        if self.state == 'confirmed':
            self.state = 'paid'
    
    def action_patient_in(self):
        """Mark patient as checked in"""
        self.write({
            'state': 'patient_in',
            'patient_in_time': fields.Datetime.now()
        })
    
    def action_start_consultation(self):
        """Start the consultation"""
        current_time = fields.Datetime.now()
        self.write({
            'state': 'in_consultation',
            'consultation_start_time': current_time
        })
        
        # For walk-in appointments, also update start_time
        if self.appointment_type == 'walkin':
            # Convert datetime to float time (hours)
            local_time = fields.Datetime.context_timestamp(self, current_time)
            start_time_float = local_time.hour + local_time.minute / 60.0
            self.start_time = start_time_float

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
            current_time = fields.Datetime.now()
            appointment.write({
                'state': 'completed',
                'consultation_end_time': current_time
            })
            
            # For walk-in appointments, also update end_time
            if appointment.appointment_type == 'walkin':
                # Convert datetime to float time (hours)
                local_time = fields.Datetime.context_timestamp(appointment, current_time)
                end_time_float = local_time.hour + local_time.minute / 60.0
                appointment.end_time = end_time_float

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
                        logging.getLogger(__name__).info('PDF created using img2pdf for appointment %s', appointment.id)
                    except Exception as e:
                        logging.getLogger(__name__).warning('img2pdf failed for appointment %s: %s', appointment.id, str(e))
                        # Fall back to Pillow
                        try:
                            from PIL import Image
                            img_buf = io.BytesIO(image_b)
                            img = Image.open(img_buf)
                            
                            # Validate image
                            if img.size[0] < 100 or img.size[1] < 100:
                                logging.getLogger(__name__).warning('Image too small for appointment %s: %s', appointment.id, img.size)
                                pdf_bytes = None
                            else:
                                # Ensure RGB for PDF
                                if img.mode in ('RGBA', 'LA'):
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    background.paste(img, mask=img.split()[-1])
                                    img = background
                                elif img.mode == 'P':
                                    img = img.convert('RGB')
                                elif img.mode != 'RGB':
                                    img = img.convert('RGB')
                                
                                # Create PDF with proper settings
                                out_buf = io.BytesIO()
                                img.save(out_buf, format='PDF', quality=95, optimize=True)
                                pdf_bytes = out_buf.getvalue()
                                logging.getLogger(__name__).info('PDF created using Pillow for appointment %s', appointment.id)
                        except Exception as e:
                            logging.getLogger(__name__).error('Pillow PDF conversion failed for appointment %s: %s', appointment.id, str(e))
                            pdf_bytes = None

                    if pdf_bytes and len(pdf_bytes) > 100:  # Ensure PDF is not empty
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
            
            # No slot template status toggling; availability is based on appointments
    
    def action_mark_no_show(self):
        """Mark patient as no-show"""
        self.write({'state': 'no_show'})
        
        # No slot template status toggling; availability is based on appointments
    
    def action_reschedule(self):
        """Open the reschedule wizard"""
        self.ensure_one()
        context = {
            'default_appointment_id': self.id,
            'default_patient_id': self.patient_id.id,
            'default_doctor_id': self.doctor_id.id,
            'default_service_id': self.service_id.id,
        }
        
        # If next_visit_date is available, pass it to the wizard
        if self.next_visit_date:
            context['default_new_date'] = self.next_visit_date
            
        return {
            'name': _('Reschedule Appointment'),
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.reschedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context
        }

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
        start_date = None
        end_date = None
        if time_filter and time_filter != 'till_now':
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
        patient_in = appointments.filtered(lambda r: r.state == 'patient_in')
        in_consultation = appointments.filtered(lambda r: r.state == 'in_consultation')
        completed = appointments.filtered(lambda r: r.state == 'completed')
        no_show = appointments.filtered(lambda r: r.state == 'no_show')
        cancelled = appointments.filtered(lambda r: r.state == 'cancelled')
        rescheduled = appointments.filtered(lambda r: r.state == 'rescheduled')
        
        # Calculate revenue from completed appointments
        total_revenue = sum(completed.mapped('consulting_fee'))

        # Count lab tests (prescription model removed; handwritten image stored on appointment)
        # total_lab_tests = sum(len(a.lab_tes) for a in appointments)

        result = {
            'total_appointments': len(appointments),
            'total_draft': len(draft),
            'total_confirmed': len(confirmed),
            'total_patient_in': len(patient_in),
            'total_in_consultation': len(in_consultation),
            'total_completed': len(completed),
            'total_no_show': len(no_show),
            'total_cancelled': len(cancelled),
            'total_rescheduled': len(rescheduled),
            'total_revenue': total_revenue,
        }
        
        _logger.info(f"Dashboard data result: {result}")
        _logger.info(f"Domain used: {domain}")
        _logger.info(f"Total appointments found: {len(appointments)}")
        
        return result
    
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
    
    # ===============================
    # Queue Management Methods
    # ===============================
    
    def _generate_queue_number(self):
        """Generate queue number for walk-in appointments"""
        self.ensure_one()
        if self.appointment_type == 'walkin':
            # Generate queue number based on date and doctor
            today_str = self.appointment_date.strftime('%Y%m%d')
            doctor_initial = self.doctor_id.name[0] if self.doctor_id.name else 'D'
            
            # Get count of walk-in appointments for this doctor today
            existing_count = self.search_count([
                ('doctor_id', '=', self.doctor_id.id),
                ('appointment_date', '=', self.appointment_date),
                ('appointment_type', '=', 'walkin'),
                ('queue_number', '!=', False)
            ])
            
            queue_num = existing_count + 1
            self.queue_number = f"{doctor_initial}{today_str}{queue_num:03d}"
    
    def action_move_to_waiting(self):
        """Move walk-in appointment to waiting state and generate queue number"""
        for appointment in self:
            if appointment.appointment_type == 'walkin' and appointment.state == 'paid':
                if not appointment.queue_number:
                    appointment._generate_queue_number()
                appointment.state = 'waiting'
    
    def get_queue_data(self, doctor_id, date):
        """Get queue data for a specific doctor and date"""
        queue_appointments = self.search([
            ('doctor_id', '=', doctor_id),
            ('appointment_date', '=', date),
            ('appointment_type', '=', 'walkin'),
            ('state', 'in', ['waiting', 'patient_in', 'in_consultation'])
        ], order='queue_number')
        
        queue_data = []
        for appointment in queue_appointments:
            queue_data.append({
                'id': appointment.id,
                'queue_number': appointment.queue_number,
                'patient_name': appointment.patient_id.name,
                'state': appointment.state,
                'queue_position': appointment.queue_position
            })
        
        return queue_data
    
    @api.model
    def get_doctor_queue_status(self, doctor_id, date=None):
        """Get current queue status for doctor dashboard"""
        if not date:
            date = fields.Date.context_today(self)
        
        waiting_count = self.search_count([
            ('doctor_id', '=', doctor_id),
            ('appointment_date', '=', date),
            ('appointment_type', '=', 'walkin'),
            ('state', '=', 'waiting')
        ])
        
        current_patient = self.search([
            ('doctor_id', '=', doctor_id),
            ('appointment_date', '=', date),
            ('state', 'in', ['patient_in', 'in_consultation'])
        ], limit=1, order='queue_number')
        
        return {
            'waiting_count': waiting_count,
            'current_patient': current_patient.patient_id.name if current_patient else None,
            'current_queue_number': current_patient.queue_number if current_patient else None
        }
