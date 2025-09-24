from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class IbcoContainer(models.Model):
    _name = "ibco.container"
    _description = "IBCO Container"
    _check_company_auto = True

    name = fields.Char(string="Container Number", required=True)
    container_volume = fields.Float(string="Volume(m³)")
    seal_no = fields.Char(string="Seal No")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", ondelete='cascade', check_company=True)
    vehicle_ids = fields.One2many('ibco.vehicle.line','container_id', string="Vehicles/Cargo")
    
    # Separate fields for vehicles and cargo
    vehicles_only_ids = fields.One2many('ibco.vehicle.line', 'container_id', string="Vehicles", 
                                       domain=[('cargo_type', '=', 'vehicle')])
    cargo_only_ids = fields.One2many('ibco.vehicle.line', 'container_id', string="Cargo", 
                                     domain=[('cargo_type', '=', 'cargo')])
    
    total_volume = fields.Float(string="Total Volume (m³)", compute='_compute_total_volume', store=True)

    @api.depends('vehicle_ids.volume_m3')
    def _compute_total_volume(self):
        for rec in self:
            rec.total_volume = sum(rec.vehicle_ids.mapped('volume_m3') or [])
    
    @api.constrains('shipment_id', 'company_id')
    def _check_shipment_company(self):
        """Ensure container company matches shipment company"""
        for rec in self:
            if rec.shipment_id and rec.shipment_id.company_id != rec.company_id:
                raise ValidationError(_("Container company must match shipment company."))
    