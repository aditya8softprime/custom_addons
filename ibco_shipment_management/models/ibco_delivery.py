from odoo import models, fields, api
from odoo.exceptions import UserError

class IbcoDelivery(models.Model):
    _name = "ibco.delivery"
    _description = "IBCO Delivery"

    name = fields.Char(string="Delivery Reference", required=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('ibco.delivery') or 'DEL')
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment")
    container_id = fields.Many2one('ibco.container', string="Container")
    vehicle_id = fields.Many2one('ibco.vehicle.line', string="Vehicle", required=True)
    customer_id = fields.Many2one('res.partner', string="Customer")
    sale_order_id = fields.Many2one('sale.order', string="Sale Order")
    invoice_id = fields.Many2one('account.move', string="Invoice")
    state = fields.Selection([
        ('draft','Draft'),
        ('in_transit','In Transit'),
        ('delivered','Delivered')
    ], default='draft', string="Status")
    delivery_date = fields.Date(string='Delivery Date')
    attachment_ids = fields.Many2many('ir.attachment', string="Delivery Documents")

    @api.onchange('vehicle_id')
    def _onchange_vehicle(self):
        if self.vehicle_id:
            self.container_id = self.vehicle_id.container_id
            self.shipment_id = self.vehicle_id.shipment_id
            self.customer_id = self.vehicle_id.customer_id
            # link sale_order if vehicle has sale_line
            if self.vehicle_id.sale_line_id:
                self.sale_order_id = self.vehicle_id.sale_line_id.order_id

    def action_set_in_transit(self):
        """Set delivery status to In Transit"""
        for rec in self:
            rec.state = 'in_transit'
    
    def action_mark_delivered(self):
        """Mark delivery as delivered - requires delivery date and documents"""
        for rec in self:
            if not rec.delivery_date:
                raise UserError("Please enter delivery date before marking as delivered.")
            rec.state = 'delivered'

    def action_set_draft(self):
        """Set delivery status back to Draft"""
        for rec in self:
            rec.state = 'draft'

    def action_mark_done(self):
        for rec in self:
            # ensure invoice is paid if linked
            if rec.invoice_id and rec.invoice_id.payment_state != 'paid':
                raise UserError("Cannot mark Done: Invoice not paid.")
            rec.state = 'done'
            # assign delivery to vehicle
            rec.vehicle_id.delivery_id = rec
