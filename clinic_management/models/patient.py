from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.translate import trans_export, trans_export_records



class ClinicPatient(models.Model):
    _name = 'clinic.patient'
    _description = 'Clinic Patient'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Patient Name', required=True, tracking=True)
    lang = fields.Selection('_get_language_list', string='Language', default='en_US')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender', tracking=True)
    age = fields.Integer(string='Age', tracking=True)
    phone = fields.Char(string='Phone', tracking=True)
    email = fields.Char(string='Email', tracking=True)
    address = fields.Text(string='Address')
    
    # Medical History fields
    has_medical_history = fields.Boolean(string='Has Medical History')
    medical_report = fields.Binary(string='Medical Report')
    medical_report_filename = fields.Char(string='Medical Report Filename')
    
    symptom = fields.Text(string='Symptoms', readonly=True,
                         help='Symptoms as reported during appointments')
    
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    
    # Related records
    appointment_ids = fields.One2many('clinic.appointment', 'patient_id', string='Appointments')
    
    appointment_count = fields.Integer(string='Appointment Count', compute='_compute_counts')

    # ticket reports

    @api.model
    def _get_language_list(self):
        """Get available languages from the system"""
        return self.env['res.lang'].get_installed()
    
    @api.depends('appointment_ids')
    def _compute_counts(self):
        for record in self:
            record.appointment_count = len(record.appointment_ids)
    
    def _get_symptoms_from_appointments(self):
        """Update symptom field based on appointment data"""
        for patient in self:
            symptoms = patient.appointment_ids.filtered(lambda a: a.symptom).mapped('symptom')
            if symptoms:
                patient.symptom = '\n'.join(symptoms)
    
    def action_view_appointments(self):
        self.ensure_one()
        return {
            'name': _('Appointments'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.appointment',
            'view_mode': 'list,form,calendar',
            'domain': [('patient_id', '=', self.id)],
            'context': {'default_patient_id': self.id},
        }
    
    @api.constrains('phone')
    def _check_duplicate_phone(self):
        """Check for duplicate phone numbers and provide user selection"""
        for record in self:
            if record.phone:
                existing_patients = self.search([
                    ('phone', '=', record.phone),
                    ('id', '!=', record.id)
                ])
                if existing_patients:
                    # For website forms, we'll handle this differently
                    # For backend forms, show the constraint error
                    if self.env.context.get('from_website'):
                        return  # Skip constraint for website forms
                    else:
                        raise ValidationError(_(
                            'A patient with phone number "%s" already exists: %s\n'
                            'Do you want to update the existing patient instead?'
                        ) % (record.phone, ', '.join(existing_patients.mapped('name'))))
    
    @api.model
    def find_or_create_patient(self, vals):
        """Find existing patient by phone or create new one"""
        phone = vals.get('phone')
        if phone:
            existing_patient = self.search([('phone', '=', phone)], limit=1)
            if existing_patient:
                # Update existing patient with new information
                existing_patient.with_context(from_website=True).write({
                    'name': vals.get('name', existing_patient.name),
                    'email': vals.get('email', existing_patient.email),
                    'age': vals.get('age', existing_patient.age),
                    'gender': vals.get('gender', existing_patient.gender),
                    'address': vals.get('address', existing_patient.address),
                })
                return existing_patient
        
        # Create new patient
        return self.with_context(from_website=True).create(vals)
    
    @api.model
    def get_patient_by_phone(self, phone):
        """Get patient information by phone number for website auto-fill"""
        if phone:
            patient = self.search([('phone', '=', phone)], limit=1)
            if patient:
                return {
                    'exists': True,
                    'name': patient.name,
                    'email': patient.email or '',
                    'age': patient.age or '',
                    'gender': patient.gender or '',
                }
        return {'exists': False}
