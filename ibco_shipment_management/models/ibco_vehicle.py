from odoo import models, fields, api

class IbcoVehicleLine(models.Model):
    _name = "ibco.vehicle.line"
    _description = "IBCO Vehicle / Cargo Line"
    _rec_name = 'chassis_no'

    name = fields.Char(string="Vehicle Description")
    chassis_no = fields.Char(string="Chassis No", required=True)
    make_model = fields.Char(string="Make/Model")
    year = fields.Char(string="Year")
    color = fields.Char(string="Color")
    volume_m3 = fields.Float(string="Volume (m³)", required=True)
    customer_id = fields.Many2one('res.partner', string="Customer")
    container_id = fields.Many2one('ibco.container', string="Container", ondelete='cascade')
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", related='container_id.shipment_id', store=True)
    sale_line_id = fields.Many2one('sale.order.line', string="Sale Order Line")
    delivery_id = fields.Many2one('ibco.delivery', string="Delivery")
    damage_ids = fields.One2many('ibco.damage', 'vehicle_id', string="Damages")
    damage_amount = fields.Monetary(string="Damage Amount", compute='_compute_damage_amount', store=True, currency_field='company_currency_id')
    allocated_expense = fields.Monetary(string="Allocated Expense", compute='_compute_allocated_expense', store=True, currency_field='company_currency_id')
    commission_amount = fields.Monetary(string="Commission Amount", compute='_compute_commission', store=True, currency_field='company_currency_id')
    final_price = fields.Monetary(string="Final Price", compute='_compute_final_price', store=True, currency_field='company_currency_id')
    profit = fields.Monetary(string="Profit", compute='_compute_profit', store=True, currency_field='company_currency_id')
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', default=lambda self: self.env.company.currency_id)

    @api.depends('damage_ids.amount')
    def _compute_damage_amount(self):
        for rec in self:
            rec.damage_amount = sum(rec.damage_ids.mapped('amount') or [0.0])

    @api.depends('container_id.total_volume','volume_m3','shipment_id.total_expense','shipment_id.expense_ids.state','shipment_id.expense_ids.total_amount')
    def _compute_allocated_expense(self):
        for rec in self:
            total_vol = rec.container_id.container_volume or 0.0
            total_exp = sum(
                rec.shipment_id.expense_ids.filtered(lambda e: e.container_id == rec.container_id).mapped('total_amount_currency') or []
            )
            if total_vol > 0:
                rec.allocated_expense = (rec.volume_m3 / total_vol) * total_exp
            else:
                rec.allocated_expense = 0.0

    @api.depends('allocated_expense','shipment_id.commission_value','shipment_id.commission_type','shipment_id.expense_ids.state','shipment_id.expense_ids.total_amount')
    def _compute_commission(self):
        for rec in self:
            sh = rec.shipment_id
            if not sh:
                rec.commission_amount = 0.0
                continue
            if sh.commission_type == 'percent':
                rec.commission_amount = (rec.allocated_expense * (sh.commission_value or 0.0)) / 100.0
            else:
                # for fixed commission: distribute fixed amount pro rata by allocated_expense
                total_allocs = sum(rec.container_id.vehicle_ids.mapped('allocated_expense') or [])
                if total_allocs > 0:
                    rec.commission_amount = (rec.allocated_expense / total_allocs) * sh.commission_value
                else:
                    # if no allocation yet, split equally
                    vehicle_count = len(rec.container_id.vehicle_ids)
                    rec.commission_amount = (sh.commission_value / vehicle_count) if vehicle_count else 0.0

    @api.depends('allocated_expense','commission_amount','shipment_id.expense_ids.state','shipment_id.expense_ids.total_amount')
    def _compute_final_price(self):
        for rec in self:
            rec.final_price = (rec.allocated_expense or 0.0) + (rec.commission_amount or 0.0)

    @api.depends('commission_amount', 'damage_amount')
    def _compute_profit(self):
        for rec in self:
            # Start with commission amount
            profit = rec.commission_amount or 0.0
            # Deduct damage amount
            rec.profit = profit - (rec.damage_amount or 0.0)    