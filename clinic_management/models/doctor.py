from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClinicDoctorSpecialTag(models.Model):
    _name = 'clinic.doctor.special.tag'
    _description = 'Doctor Special Tags'
    
    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index')


class DoctorShiftConfig(models.Model):
    _name = 'doctor.shift.config'
    _description = 'Doctor Weekly Shift Configuration'
    _order = 'doctor_id, day_id, shift_type'

    doctor_id = fields.Many2one('clinic.doctor', string="Doctor", required=True, ondelete="cascade")
    # Replaced selection with Many2one to clinic.days
    day_id = fields.Many2one('clinic.days', string='Day', required=True)
    shift_type = fields.Selection([('morning', 'Morning'), ('evening', 'Evening')], string="Shift Type", required=True)
    start_time = fields.Float("Start Time (Hour, e.g., 8.0)", required=True)
    end_time = fields.Float("End Time (Hour, e.g., 12.0)", required=True)
    slot_duration = fields.Integer("Slot Duration (Minutes)", default=30)
    active = fields.Boolean("Active", default=True)
    
    # Relations
    slot_ids = fields.One2many('clinic.slot', 'shift_config_id', string="Generated Slots")
    
    # Computed fields
    slot_count = fields.Integer("Total Slots", compute='_compute_slot_count')
    
    @api.depends('slot_ids')
    def _compute_slot_count(self):
        for config in self:
            config.slot_count = len(config.slot_ids)
    
    _sql_constraints = [
        # Updated unique constraint to use day_id instead of day_of_week
        ('unique_doctor_day_shift', 'unique(doctor_id, day_id, shift_type)', 
         'Only one shift configuration per day per shift type allowed for each doctor!')
    ]

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for config in self:
            if config.start_time >= config.end_time:
                raise ValidationError(_("End Time must be greater than Start Time"))

    @api.constrains('slot_duration')
    def _check_slot_duration(self):
        for config in self:
            if config.slot_duration <= 0:
                raise ValidationError(_("Slot Duration must be greater than 0"))

    def _generate_slots(self):
        """Generate slot records based on config"""
        self.ensure_one()
        if not self.active:
            return
            
        Slot = self.env['clinic.slot']
        slots_to_create = []
        
        current = self.start_time * 60  # convert hr -> minutes
        end = self.end_time * 60
        slot_number = 1
        
        while current < end:
            start_min = current
            end_min = min(current + self.slot_duration, end)

            start_time_float = start_min / 60
            end_time_float = end_min / 60
            
            start_label = f"{int(start_min//60):02d}:{int(start_min%60):02d}"
            end_label = f"{int(end_min//60):02d}:{int(end_min%60):02d}"
            slot_label = f"{start_label} - {end_label}"
            
            # Generate slot number based on clinic.days code and shift
            day_code = (self.day_id.code or '').upper()
            shift_code = 'M' if self.shift_type == 'morning' else 'E'
            slot_number_str = f"{day_code}-{shift_code}-{slot_number:03d}"

            # Map clinic.days to python weekday index (0=Mon .. 6=Sun)
            day_of_week = False
            if self.day_id and self.day_id.sequence:
                # days_master_data.xml defines Monday..Sunday with sequence 1..7
                day_of_week = str(int(self.day_id.sequence) - 1)

            slots_to_create.append({
                'doctor_id': self.doctor_id.id,
                'shift_config_id': self.id,
                # Keep backward compatibility fields on clinic.slot
                'day_id': self.day_id.id,
                'shift': self.shift_type,
                # New weekly template fields
                'day_of_week': day_of_week,
                'shift_type': self.shift_type,
                'start_time_float': start_time_float,  # Keep for compatibility
                'end_time_float': end_time_float,      # Keep for compatibility
                'start_time': start_label,
                'end_time': end_label,
                'slot_label': slot_label,
                'slot_number': slot_number_str,
                'duration': self.slot_duration,
                'status': 'available',
            })
            
            current = end_min
            slot_number += 1
            
        # Create all slots at once for better performance
        if slots_to_create:
            Slot.create(slots_to_create)


class ClinicDoctor(models.Model):
    _name = 'clinic.doctor'
    _description = 'Clinic Doctor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, id'
    
    name = fields.Char(string='Doctor Name', required=True, tracking=True, index=True)
    image = fields.Binary(string='Profile Image')
    specialization_ids = fields.Many2many(
        'clinic.service', 
        string='Specializations',
        help='Medical specializations of the doctor',
        tracking=True,
    )
    qualification = fields.Text(string='Qualification', tracking=True)
    license_no = fields.Char(string='License No', tracking=True, index=True)
    mobile = fields.Char(string='Mobile', tracking=True)
    email = fields.Char(string='Email', tracking=True)
    department = fields.Many2one('hr.department', string='Department', tracking=True, index=True)
    available_days = fields.Many2many('clinic.days', string='Available Days', tracking=True)
    
    # Morning shift configuration
    morning_shift = fields.Boolean(string='Morning Shift Available', default=True, tracking=True)
    morning_start_time = fields.Float(string='Morning Start Time', tracking=True)
    morning_end_time = fields.Float(string='Morning End Time', tracking=True)
    
    # Evening shift configuration
    evening_shift = fields.Boolean(string='Evening Shift Available', default=False, tracking=True)
    evening_start_time = fields.Float(string='Evening Start Time', tracking=True)
    evening_end_time = fields.Float(string='Evening End Time', tracking=True)
    
    slot_duration = fields.Selection([
        ('15', '15 minutes'),
        ('20', '20 minutes'),
        ('30', '30 minutes'),
        ('45', '45 minutes'),
        ('60', '60 minutes'),
    ], string='Slot Duration', default='30', tracking=True)
    bio = fields.Html(string='Bio/Description')  # Removed tracking as it's not supported for HTML fields
    special_tag_ids = fields.Many2many('clinic.doctor.special.tag', string='Special Tags')
    consultation_fee = fields.Monetary(string='Consultation Fee', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company, index=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Related User', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Related Employee', tracking=True)
    
    # Relations
    shift_config_ids = fields.One2many('doctor.shift.config', 'doctor_id', string="Shift Configurations")
    slot_ids = fields.One2many('clinic.slot', 'doctor_id', string="Generated Slots")
    appointment_ids = fields.One2many('clinic.appointment', 'doctor_id', string='Appointments')
    holiday_ids = fields.One2many('clinic.holiday', 'doctor_id', string='Leaves/Holidays')
    
    # New fields for a more professional doctor profile
    website = fields.Char(string='Website')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender')
    date_of_birth = fields.Date(string='Date of Birth')
    experience_years = fields.Integer(string='Years of Experience')
    languages = fields.Many2many('res.lang', string='Languages Spoken')
    registration_date = fields.Date(string='Registration Date', default=fields.Date.today, tracking=True)
    
    _sql_constraints = [
        ('license_no_uniq', 'unique(license_no)', 'License number must be unique!')
    ]
    
    def name_get(self):
        """Custom name_get to show qualification with doctor name"""
        result = []
        for doctor in self:
            name = doctor.name
            if doctor.qualification:
                qualification_summary = doctor.qualification.split('\n')[0] if '\n' in doctor.qualification else doctor.qualification
                name = f"{name} ({qualification_summary})"
            result.append((doctor.id, name))
        return result

    def get_consultation_product_vals(self):
        """Return generic consultation product and dynamic price for this doctor"""
        self.ensure_one()
        Product = self.env['product.product']

        # Search for generic Consultation product
        product = Product.search([('name', '=', 'Consultation')], limit=1)
        if not product:
            raise ValidationError(_('Please create a generic Consultation product first!'))

        return {
            'product': product,
            'price_unit': self.consultation_fee,
            'description': f"Consultation – {self.name}"
        }
    
    @api.constrains('morning_start_time', 'morning_end_time', 'morning_shift')
    def _check_morning_hours(self):
        for record in self:
            if record.morning_shift and record.morning_start_time >= record.morning_end_time:
                raise ValidationError(_('Morning End Time must be greater than Morning Start Time'))
    
    @api.constrains('evening_start_time', 'evening_end_time', 'evening_shift')
    def _check_evening_hours(self):
        for record in self:
            if record.evening_shift and record.evening_start_time >= record.evening_end_time:
                raise ValidationError(_('Evening End Time must be greater than Evening Start Time'))
    
    @api.constrains('morning_shift', 'evening_shift')
    def _check_at_least_one_shift(self):
        for record in self:
            if not record.morning_shift and not record.evening_shift:
                raise ValidationError(_('At least one shift (Morning or Evening) must be enabled'))
    
    @api.model_create_multi
    def create(self, vals_list):
        doctors = super(ClinicDoctor, self).create(vals_list)
        # Create slots for each doctor
        for doctor in doctors:
            doctor._create_slots()
        return doctors
    
    def write(self, vals):
        res = super(ClinicDoctor, self).write(vals)
        # If availability related fields changed, update slots
        slot_related_fields = ['available_days', 'morning_start_time', 'morning_end_time', 
                              'evening_start_time', 'evening_end_time', 'morning_shift', 
                              'evening_shift', 'slot_duration']
        if any(field in vals for field in slot_related_fields):
            self._create_slots()
        return res
    
    def generate_weekly_slots(self):
        """Loop over shift_config_ids and generate slots in clinic.slot"""
        for doctor in self:
            # Clear old available slots only (preserve booked/historical slots)
            doctor.slot_ids.filtered(lambda s: s.status == 'available').unlink()
            for config in doctor.shift_config_ids:
                config._generate_slots()

    def _create_slots(self):
        """Generate slots based on doctor's availability (Legacy method - now uses shift configs)"""
        self.ensure_one()
        # If we have shift configurations, use the new system
        if self.shift_config_ids:
            self.generate_weekly_slots()
            return
            
        # Legacy slot generation for backward compatibility
        Slot = self.env['clinic.slot']
        
        # Delete existing slots that are in 'available' status only
        # This preserves historical data of booked slots
        existing_slots = Slot.search([
            ('doctor_id', '=', self.id),
            ('status', '=', 'available')
        ])
        existing_slots.unlink()
        
        # Convert slot_duration from string to float
        slot_duration_minutes = float(self.slot_duration)
        slot_duration_hours = slot_duration_minutes / 60
        
        # Create new slots for each available day
        for day in self.available_days:
            slot_number = 1
            
            # Morning shift slots
            if self.morning_shift and self.morning_start_time and self.morning_end_time:
                current_time = self.morning_start_time
                
                while current_time + slot_duration_hours <= self.morning_end_time:
                    end_time = current_time + slot_duration_hours
                    
                    # Create morning slot
                    slot_vals = {
                        'doctor_id': self.id,
                        'day_id': day.id,
                        'start_time': current_time,
                        'end_time': end_time,
                        'duration': slot_duration_minutes,
                        'shift': 'morning',
                        'slot_number': f"{day.code}-M-{slot_number:03d}",
                        'status': 'available',
                    }
                    Slot.create(slot_vals)
                    
                    # Move to next slot
                    current_time = end_time
                    slot_number += 1
            
            # Reset slot number for evening shift
            slot_number = 1
            
            # Evening shift slots
            if self.evening_shift and self.evening_start_time and self.evening_end_time:
                current_time = self.evening_start_time
                
                while current_time + slot_duration_hours <= self.evening_end_time:
                    end_time = current_time + slot_duration_hours
                    
                    # Create evening slot
                    slot_vals = {
                        'doctor_id': self.id,
                        'day_id': day.id,
                        'start_time': current_time,
                        'end_time': end_time,
                        'duration': slot_duration_minutes,
                        'shift': 'evening',
                        'slot_number': f"{day.code}-E-{slot_number:03d}",
                        'status': 'available',
                    }
                    Slot.create(slot_vals)
                    
                    # Move to next slot
                    current_time = end_time
                    slot_number += 1
    
    def action_create_employee(self):
        """Create an employee record for this doctor"""
        self.ensure_one()
        if self.employee_id:
            raise ValidationError(_('Employee already exists for this doctor'))
        
        # Create employee
        employee = self.env['hr.employee'].create({
            'name': self.name,
            'work_email': self.email,
            'mobile_phone': self.mobile,
            'department_id': self.department.id if self.department else False,
            'company_id': self.company_id.id,
            'gender': self.gender,
            'birthday': self.date_of_birth,
        })
        
        self.employee_id = employee.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Employee'),
            'res_model': 'hr.employee',
            'res_id': employee.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_create_user(self):
        """Create a user account for this doctor"""
        self.ensure_one()
        if self.user_id:
            raise ValidationError(_('User already exists for this doctor'))
        
        # Create user
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': self.name,
            'login': self.email,
            'email': self.email,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,  # Internal user mandatory
                self.env.ref('clinic_management.group_clinic_doctor').id,  # Custom doctor group
            ])],
            'company_ids': [(4, self.company_id.id)],
            'company_id': self.company_id.id,
        })
        
        self.user_id = user.id
        
        # Link employee to user if employee exists
        if self.employee_id:
            self.employee_id.user_id = user.id
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('User'),
            'res_model': 'res.users',
            'res_id': user.id,
            'view_mode': 'form',
            'target': 'current',
        }

