from odoo import models, fields


class ClinicLabTest(models.Model):
    _name = 'clinic.lab.test'
    _description = 'Lab Test'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Test Name', required=True)
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True)
    appointment_id = fields.Many2one('clinic.appointment', string='Appointment')
    test_date = fields.Date(string='Date', default=fields.Date.context_today)
    notes = fields.Text(string='Notes')
    result = fields.Text(string='Result')
    result_document = fields.Binary(string='Result Document')
    result_document_filename = fields.Char(string='Result Document Filename')

    state = fields.Selection([
        ('requested', 'Requested'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='requested', tracking=True)

    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)

    def action_complete(self):
        self.write({'state': 'completed'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})
