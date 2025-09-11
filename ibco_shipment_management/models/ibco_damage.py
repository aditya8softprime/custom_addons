from odoo import models, fields, _

class IbcoDamage(models.Model):
    _name = "ibco.damage"
    _description = "IBCO Damage Expense"

    name = fields.Char(string="Damage Description")
    amount = fields.Monetary(string="Amount", required=True, currency_field='company_currency_id')
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", ondelete='cascade')
    vehicle_id = fields.Many2one('ibco.vehicle.line', string="Vehicle", ondelete='cascade')
    date = fields.Date(string='Date')
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', default=lambda self: self.env.company.currency_id)
    attachment_ids = fields.Many2many('ir.attachment', string="Attachments")
