from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClinicDoctorSpecialTag(models.Model):
    _name = 'clinic.doctor.special.tag'
    _description = 'Doctor Special Tags'
    
    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index')



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
    working_start_time = fields.Float(string='Working Start Time', tracking=True)
    working_end_time = fields.Float(string='Working End Time', tracking=True)
    slot_duration = fields.Selection([
        ('15', '15 minutes'),
        ('20', '20 minutes'),
        ('30', '30 minutes'),
        ('45', '45 minutes'),
        ('60', '60 minutes'),
    ], string='Slot Duration', default='30', tracking=True)
    max_patients_per_slot = fields.Integer(string='Max Patients Per Slot', default=1, tracking=True)
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
    
    # Statistics and related records
    slot_ids = fields.One2many('clinic.slot', 'doctor_id', string='Slots')
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
    @api.constrains('working_start_time', 'working_end_time')
    def _check_working_hours(self):
        for record in self:
            if record.working_start_time >= record.working_end_time:
                raise ValidationError(_('Working End Time must be greater than Working Start Time'))
    
    @api.constrains('max_patients_per_slot')
    def _check_max_patients(self):
        for record in self:
            if record.max_patients_per_slot <= 0:
                raise ValidationError(_('Maximum patients per slot must be greater than 0'))
    
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
        slot_related_fields = ['available_days', 'working_start_time', 'working_end_time', 
                              'slot_duration', 'max_patients_per_slot']
        if any(field in vals for field in slot_related_fields):
            self._create_slots()
        return res
    
    def _create_slots(self):
        """Generate slots based on doctor's availability"""
        self.ensure_one()
        Slot = self.env['clinic.slot']
        
        # Delete existing slots that are in 'available' status only
        # This preserves historical data of booked slots
        existing_slots = Slot.search([
            ('doctor_id', '=', self.id),
            ('status', '=', 'available')
        ])
        existing_slots.unlink()
        
        # Create new slots
        for day in self.available_days:
            current_time = self.working_start_time
            slot_number = 1
            
            # Convert slot_duration from string to float
            slot_duration_minutes = float(self.slot_duration)
            
            while current_time + (slot_duration_minutes / 60) <= self.working_end_time:
                end_time = current_time + (slot_duration_minutes / 60)
                
                # Create slot
                slot_vals = {
                    'doctor_id': self.id,
                    'day_id': day.id,
                    'start_time': current_time,
                    'end_time': end_time,
                    'duration': slot_duration_minutes,
                    'max_patients': self.max_patients_per_slot,
                    'slot_number': f"{day.code}-{slot_number:03d}",
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
