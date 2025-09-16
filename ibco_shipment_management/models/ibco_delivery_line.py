from odoo import models, fields, api
from odoo.exceptions import UserError

class IbcoDeliveryLine(models.Model):
    _name = "ibco.delivery.line"
    _description = "IBCO Delivery Line"
    _check_company_auto = True

    delivery_id = fields.Many2one('ibco.delivery', string="Delivery", required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Company', related='delivery_id.company_id', store=True)
    container_id = fields.Many2one('ibco.container', string="Container", required=True, check_company=True)
    vehicle_id = fields.Many2one('ibco.vehicle.line', string="Vehicle/cargo", required=True, check_company=True)
    sequence = fields.Integer(string="Sequence", default=10)

    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        if self.vehicle_id:
            self.container_id = self.vehicle_id.container_id

    @api.constrains('delivery_id', 'vehicle_id')
    def _check_unique_vehicle(self):
        for line in self:
            if line.vehicle_id:
                existing = self.search([
                    ('delivery_id', '!=', line.delivery_id.id),
                    ('vehicle_id', '=', line.vehicle_id.id)
                ])
                if existing:
                    raise UserError(f"Vehicle {line.vehicle_id.chassis_no} is already assigned to another delivery.")

    _sql_constraints = [
        ('unique_vehicle_per_delivery', 'unique(delivery_id, vehicle_id)', 'Vehicle can only appear once per delivery.'),
    ]
