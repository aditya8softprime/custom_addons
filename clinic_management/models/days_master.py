from odoo import models, fields


class ClinicDays(models.Model):
    _name = 'clinic.days'
    _description = 'Clinic Working Days'
    _order = 'sequence'
    
    name = fields.Char(string='Day Name', required=True)
    code = fields.Char(string='Day Code', required=True, size=3)
    sequence = fields.Integer(string='Sequence', default=10)
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Day name must be unique!'),
        ('code_uniq', 'unique(code)', 'Day code must be unique!')
    ]
