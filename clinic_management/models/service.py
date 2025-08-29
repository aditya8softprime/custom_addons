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
    color = fields.Integer(string='Color Index')
    
    appointment_count = fields.Integer(string='Appointment Count', compute='_compute_appointment_count')
    
    def _compute_appointment_count(self):
        """Compute the number of appointments for this service"""
        for service in self:
            service.appointment_count = self.env['clinic.appointment'].search_count([
                ('service_id', '=', service.id)
            ])
    
    def action_view_appointments(self):
        """Action to view appointments related to this service"""
        self.ensure_one()
        return {
            'name': _('Appointments'),
            'type': 'ir.actions.act_window',
            'res_model': 'clinic.appointment',
            'view_mode': 'list,form,calendar',
            'domain': [('service_id', '=', self.id)],
            'context': {'default_service_id': self.id},
        }
