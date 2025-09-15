from odoo import models, fields, api


class HrExpense(models.Model):
    _inherit = "hr.expense"

    shipment_id = fields.Many2one(
        'ibco.shipment', 
        string="Shipment",
        help="Link this expense to a specific shipment"
    )
    container_id = fields.Many2one(
        'ibco.container', 
        string="Container",
        help="Link this expense to a specific container within the shipment"
    )

    @api.onchange('shipment_id')
    def _onchange_shipment_id(self):
        """Clear container when shipment changes"""
        if self.shipment_id:
            # Limit container selection to containers in the selected shipment
            return {
                'domain': {
                    'container_id': [('shipment_id', '=', self.shipment_id.id)]
                }
            }
        else:
            self.container_id = False
            return {
                'domain': {
                    'container_id': []
                }
            }
