from odoo import models, fields, api


class HrExpense(models.Model):
    _inherit = "hr.expense"

    shipment_id = fields.Many2one(
        'ibco.shipment', 
        string="Shipment",
        help="Link this expense to a specific shipment",
        check_company=True
    )
    container_id = fields.Many2one(
        'ibco.container', 
        string="Container",
        domain="[('shipment_id', '=', shipment_id)]",
        help="Link this expense to a specific container within the shipment",
        check_company=True
    )
    vehicle_id = fields.Many2one(
        'ibco.vehicle.line', 
        string="Vehicle/Cargo",
        domain="[('shipment_id', '=', shipment_id)]",
        help="Link this expense to a specific vehicle/cargo within the container",
        check_company=True
    )

    is_damage_expense = fields.Boolean(
        string="Is Damage Expense",default=False,
        help="Indicates if this expense is related to a damage record"
    )
