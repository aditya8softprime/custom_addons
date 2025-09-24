from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class IbcoArrivalShipment(models.Model):
    _name = "ibco.arrival.shipment"
    _description = "IBCO Arrival Shipment Tracking"
    _order = "arrival_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Local Manifest", required=True, copy=False, 
                      default=lambda self: self.env['ir.sequence'].next_by_code('ibco.arrival.shipment') or 'New')
    vessel_name = fields.Char(string="Vessel Name", required=True)
    arrival_date = fields.Date(string="Arrival Date", required=True, default=fields.Date.context_today)
    
    # Reference to original shipment (optional)
    shipment_id = fields.Many2one('ibco.shipment', string="Reference Shipment", 
                                 help="Link to original shipment if available")
    
    company_id = fields.Many2one('res.company', string='Company', required=True, 
                               default=lambda self: self.env.company)
    
    # Arrival tracking fields
    arrival_container_ids = fields.One2many('ibco.arrival.container', 'arrival_shipment_id', 
                                          string="Arrival Containers")
    
    # Summary fields
    total_containers = fields.Integer(string="Total Containers", compute='_compute_summary', store=True)
    total_cargo_lines = fields.Integer(string="Total Cargo Lines", compute='_compute_summary', store=True)
    total_quantity = fields.Float(string="Total Quantity", compute='_compute_summary', store=True, digits=(16, 2))
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed')
    ], default='draft', string="Status")
    
    # Additional info
    notes = fields.Text(string="Notes")
    
    @api.depends('arrival_container_ids', 'arrival_container_ids.cargo_line_ids', 'arrival_container_ids.cargo_line_ids.quantity')
    def _compute_summary(self):
        for record in self:
            record.total_containers = len(record.arrival_container_ids)
            total_cargo_lines = 0
            total_quantity = 0.0
            
            for container in record.arrival_container_ids:
                total_cargo_lines += len(container.cargo_line_ids)
                total_quantity += sum(container.cargo_line_ids.mapped('quantity') or [])
            
            record.total_cargo_lines = total_cargo_lines
            record.total_quantity = total_quantity
    
    def action_confirm(self):
        """Confirm arrival record"""
        self.ensure_one()
        if not self.arrival_container_ids:
            raise ValidationError(_("Please add at least one container before confirming."))
        self.state = 'confirmed'
    
    def action_complete(self):
        """Complete arrival record"""
        self.ensure_one()
        self.state = 'completed'
    
    def action_reset_to_draft(self):
        """Reset to draft"""
        self.ensure_one()
        self.state = 'draft'


class IbcoArrivalContainer(models.Model):
    _name = "ibco.arrival.container"
    _description = "IBCO Arrival Container"
    _check_company_auto = True

    name = fields.Char(string="Container Number", required=True)
    arrival_shipment_id = fields.Many2one('ibco.arrival.shipment', string="Arrival Shipment", 
                                        ondelete='cascade', required=True)
    
    # Container details
    marks = fields.Char(string="Marks")
    seal_no = fields.Char(string="Seal No")
    
    # Cargo lines in this container
    cargo_line_ids = fields.One2many('ibco.arrival.cargo.line', 'arrival_container_id', 
                                   string="Cargo Lines")
    
    # Summary for container
    total_cargo_lines = fields.Integer(string="Total Cargo Lines", compute='_compute_container_summary', store=True)
    total_quantity = fields.Float(string="Total Quantity", compute='_compute_container_summary', store=True, digits=(16, 2))
    
    company_id = fields.Many2one('res.company', string='Company', 
                               related='arrival_shipment_id.company_id', store=True)
    
    @api.depends('cargo_line_ids', 'cargo_line_ids.quantity')
    def _compute_container_summary(self):
        for record in self:
            record.total_cargo_lines = len(record.cargo_line_ids)
            record.total_quantity = sum(record.cargo_line_ids.mapped('quantity') or [])
    

class IbcoArrivalCargoLine(models.Model):
    _name = "ibco.arrival.cargo.line"
    _description = "IBCO Arrival Cargo Line"
    _check_company_auto = True

    arrival_container_id = fields.Many2one('ibco.arrival.container', string="Arrival Container", 
                                         ondelete='cascade', required=True)
    arrival_shipment_id = fields.Many2one('ibco.arrival.shipment', string="Arrival Shipment",
                                        related='arrival_container_id.arrival_shipment_id', store=True)
    
    # Simple cargo details - only description and quantity as requested
    description = fields.Char(string="Description", required=True, 
                            help="Cargo description like SPER PARTS, COSMATIC, GENERAL CARGO, etc.")
    quantity = fields.Float(string="Quantity", required=True, digits=(16, 2),
                          help="Quantity like 95, 98, 272, etc.")
    
    company_id = fields.Many2one('res.company', string='Company', 
                               related='arrival_container_id.company_id', store=True)