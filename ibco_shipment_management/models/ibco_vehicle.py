from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class IbcoVehicleLine(models.Model):
    _name = "ibco.vehicle.line"
    _description = "IBCO Vehicle / Cargo Line"
    _rec_name = 'display_name'
    _check_company_auto = True

    # Cargo/Vehicle Type Selection
    cargo_type = fields.Selection([
        ('vehicle', 'Vehicle'),
        ('cargo', 'Cargo')
    ], string="Type", required=True, default='vehicle', help="Select whether this is a vehicle or cargo")
    
    # Common fields for both vehicle and cargo
    name = fields.Char(string="Description", help="Vehicle or cargo description")
    display_name = fields.Char(string="Display Name", compute='_compute_display_name', store=True)
    
    # Vehicle-specific fields
    chassis_no = fields.Char(string="Chassis No", help="Vehicle chassis number (for vehicles only)")
    make_model = fields.Char(string="Make/Model", help="Vehicle make and model")
    year = fields.Char(string="Year", help="Vehicle manufacturing year")
    color = fields.Char(string="Color", help="Vehicle color")
    
    # Cargo-specific fields
    cargo_description = fields.Text(string="Cargo Description", help="Detailed description of cargo contents")
    cargo_weight = fields.Float(string="Weight (kg)", help="Cargo weight in kilograms")
    cargo_category = fields.Selection([
        ('electronics', 'Electronics'),
        ('furniture', 'Furniture'),
        ('machinery', 'Machinery'),
        ('textiles', 'Textiles'),
        ('food', 'Food & Beverages'),
        ('automotive_parts', 'Automotive Parts'),
        ('industrial', 'Industrial Equipment'),
        ('personal_effects', 'Personal Effects'),
        ('other', 'Other')
    ], string="Cargo Category", help="Category of cargo being shipped")
    is_hazardous = fields.Boolean(string="Hazardous Material", help="Check if cargo contains hazardous materials")
    
    # Common fields continued
    volume_m3 = fields.Float(string="Volume (m³)", required=True)
    customer_id = fields.Many2one('res.partner', string="Customer")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    container_id = fields.Many2one('ibco.container', string="Container", ondelete='cascade', check_company=True)
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", related='container_id.shipment_id', store=True)
    sale_line_id = fields.Many2one('sale.order.line', string="Sale Order Line")
    delivery_id = fields.Many2one('ibco.delivery', string="Delivery")
    damage_ids = fields.One2many('ibco.damage', 'vehicle_id', string="Damages")
    
    # Financial fields (converted from Monetary to Float)
    damage_amount = fields.Float(string="Damage Amount", compute='_compute_damage_amount', store=True, digits=(16, 2))
    allocated_expense = fields.Float(string="Allocated Expense", compute='_compute_allocated_expense', store=True, digits=(16, 2))
    commission_amount = fields.Float(string="Commission Amount", digits=(16, 2))
    final_price = fields.Float(string="Final Price", compute='_compute_final_price', store=True, digits=(16, 2))
    profit = fields.Float(string="Profit", compute='_compute_profit', store=True, digits=(16, 2))

    @api.depends('cargo_type', 'chassis_no', 'name', 'cargo_description')
    def _compute_display_name(self):
        """Compute display name based on cargo type"""
        for rec in self:
            if rec.cargo_type == 'vehicle':
                if rec.chassis_no:
                    rec.display_name = rec.chassis_no
                elif rec.name:
                    rec.display_name = rec.name
                else:
                    rec.display_name = 'Vehicle'
            else:  # cargo
                if rec.name:
                    rec.display_name = rec.name
                elif rec.cargo_description:
                    # Take first 50 characters of cargo description
                    rec.display_name = rec.cargo_description[:50] + ('...' if len(rec.cargo_description) > 50 else '')
                else:
                    rec.display_name = 'Cargo'
    
    @api.onchange('cargo_type')
    def _onchange_cargo_type(self):
        """Clear type-specific fields when cargo type changes"""
        if self.cargo_type == 'vehicle':
            # Clear cargo-specific fields
            self.cargo_description = False
            self.cargo_weight = 0.0
            self.cargo_category = False
            self.is_hazardous = False
        else:  # cargo
            # Clear vehicle-specific fields
            self.chassis_no = False
            self.make_model = False
            self.year = False
            self.color = False

    @api.constrains('cargo_type', 'chassis_no', 'name')
    def _check_required_fields(self):
        """Validate required fields based on cargo type"""
        for rec in self:
            if rec.cargo_type == 'vehicle' and not rec.chassis_no:
                if not rec.name:
                    raise ValidationError("Vehicle must have either a Chassis Number or Description.")
            elif rec.cargo_type == 'cargo' and not rec.name:
                raise ValidationError("Cargo must have a Description.")
    
    @api.constrains('container_id', 'company_id')
    def _check_container_company(self):
        """Ensure vehicle company matches container company"""
        for rec in self:
            if rec.container_id and rec.container_id.company_id != rec.company_id:
                raise ValidationError(_("Vehicle/Cargo company must match container company."))

    @api.depends('damage_ids.amount')
    def _compute_damage_amount(self):
        for rec in self:
            rec.damage_amount = sum(rec.damage_ids.mapped('amount') or [0.0])

    @api.depends('container_id.total_volume','volume_m3','shipment_id.total_expense','shipment_id.expense_ids','shipment_id.expense_ids.total_amount')
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

    @api.depends('allocated_expense','commission_amount')
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