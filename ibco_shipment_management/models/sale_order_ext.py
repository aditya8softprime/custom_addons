from odoo import models, fields, api

class SaleOrderLineExt(models.Model):
    _inherit = 'sale.order.line'

    vehicle_id = fields.Many2one('ibco.vehicle.line', string='Vehicle')
    delivery_id = fields.Many2one('ibco.delivery', string='Delivery')

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        if self.vehicle_id:
            self.name = self.vehicle_id.name or self.name
            # set price unit from vehicle.final_price if desired
            self.price_unit = self.vehicle_id.final_price or self.price_unit
