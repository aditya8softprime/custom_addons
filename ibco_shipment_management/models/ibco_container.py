from odoo import models, fields, api

class IbcoContainer(models.Model):
    _name = "ibco.container"
    _description = "IBCO Container"

    name = fields.Char(string="Container Number", required=True)
    container_type = fields.Selection([('20ft','20ft'),('40ft','40ft')], string="Container Type")
    seal_no = fields.Char(string="Seal No")
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", ondelete='cascade')
    vehicle_ids = fields.One2many('ibco.vehicle.line','container_id', string="Vehicles/Cargo")
    expense_ids = fields.One2many('ibco.expense','container_id', string="Container Expenses")

    total_volume = fields.Float(string="Total Volume (m³)", compute='_compute_total_volume', store=True)

    @api.depends('vehicle_ids.volume_m3')
    def _compute_total_volume(self):
        for rec in self:
            rec.total_volume = sum(rec.vehicle_ids.mapped('volume_m3') or [])
    