from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
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
