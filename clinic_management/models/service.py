from odoo import models, fields, api, _


class ClinicService(models.Model):
    _name = 'clinic.service'
    _description = 'Clinic Services/Treatments'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Service Name', required=True, tracking=True)
    description = fields.Html(string='Description')  # Removed tracking as it's not supported for HTML fields
    icon = fields.Binary(string='Service Icon/Image')
    active = fields.Boolean(string='Active', default=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    price = fields.Monetary(string='Price', currency_field='currency_id', tracking=True)
    color = fields.Integer(string='Color Index')
    
    doctor_ids = fields.Many2many(
        'clinic.doctor', 
        string='Doctors',
        compute='_compute_doctor_ids', 
        store=True,
    )
    appointment_count = fields.Integer(string='Appointment Count', compute='_compute_appointment_count')
    
    @api.depends()
    def _compute_doctor_ids(self):
        """Compute all doctors who offer this service"""
        for service in self:
            service.doctor_ids = self.env['clinic.doctor'].search([
                ('specialization_ids', 'in', service.id),
                ('active', '=', True)
            ])
    
    def _compute_appointment_count(self):
        """Compute the number of appointments for this service"""
        for service in self:
            # This will need to be adjusted based on how services are linked to appointments
            # For now, assuming appointments are linked to doctors who offer this service
            service.appointment_count = self.env['clinic.appointment'].search_count([
                ('doctor_id', 'in', service.doctor_ids.ids)
            ])
    
    def action_view_appointments(self):
        """Action to view appointments related to this service"""
        self.ensure_one()
        return {
            'name': _('Appointments'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.appointment',
            'view_mode': 'list,form,calendar',
            'domain': [('doctor_id', 'in', self.doctor_ids.ids)],
            'context': {'default_doctor_id': self.doctor_ids[0].id if self.doctor_ids else False},
        }
