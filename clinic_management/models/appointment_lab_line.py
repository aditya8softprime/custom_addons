from odoo import models, fields, api


class AppointmentLabLine(models.Model):
    _name = 'appointment.lab.line'
    _description = 'Lab Test Line in Appointment'
    _order = 'sequence, id'

    appointment_id = fields.Many2one(
        'clinic.appointment', 
        string='Appointment', 
        required=True, 
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    test_name = fields.Char(string='Test Name', required=True)
    notes = fields.Text(string='Instructions/Notes')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True)
    
    # Result can be either text or file upload
    result_text = fields.Text(string='Result (Text)')
    result_file = fields.Binary(string='Result File (PDF/Image)')
    result_filename = fields.Char(string='Filename')
    
    # Additional fields
    date_requested = fields.Datetime(string='Date Requested', default=fields.Datetime.now)
    date_completed = fields.Datetime(string='Date Completed')
    cost = fields.Float(string='Cost', default=0.0)
    
    @api.onchange('state')
    def _onchange_state(self):
        """Update completion date when state changes to completed"""
        if self.state == 'completed' and not self.date_completed:
            self.date_completed = fields.Datetime.now()
        elif self.state != 'completed':
            self.date_completed = False
