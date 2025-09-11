from odoo import models, fields, api
from odoo.exceptions import UserError

class IbcoDelivery(models.Model):
    _name = "ibco.delivery"
    _description = "IBCO Delivery"

    name = fields.Char(string="Delivery Reference", required=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('ibco.delivery') or 'DEL')
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment")
    customer_id = fields.Many2one('res.partner', string="Customer", required=True)
    sale_order_id = fields.Many2one('sale.order', string="Sale Order")
    invoice_id = fields.Many2one('account.move', string="Invoice")
    delivery_line_ids = fields.One2many('ibco.delivery.line', 'delivery_id', string="Delivery Lines")
    state = fields.Selection([
        ('draft','Draft'),
        ('in_transit','In Transit'),
        ('delivered','Delivered')
    ], default='draft', string="Status")
    delivery_date = fields.Date(string='Delivery Date')
    attachment_ids = fields.Many2many('ir.attachment', string="Delivery Documents")

    def action_set_in_transit(self):
        """Set delivery status to In Transit"""
        for rec in self:
            if not rec.delivery_line_ids:
                raise UserError("Please add at least one delivery line before setting to In Transit.")
            rec.state = 'in_transit'
    
    def action_mark_delivered(self):
        """Mark delivery as delivered - requires delivery date and documents"""
        for rec in self:
            if not rec.delivery_line_ids:
                raise UserError("Please add at least one delivery line before marking as delivered.")
            if not rec.delivery_date:
                raise UserError("Please enter delivery date before marking as delivered.")
            rec.state = 'delivered'

    def action_set_draft(self):
        """Set delivery status back to Draft"""
        for rec in self:
            rec.state = 'draft'

    def action_mark_done(self):
        for rec in self:
            if not rec.delivery_line_ids:
                raise UserError("Please add at least one delivery line before marking as done.")
            # ensure invoice is paid if linked
            if rec.invoice_id and rec.invoice_id.payment_state != 'paid':
                raise UserError("Cannot mark Done: Invoice not paid.")
            rec.state = 'done'
            # assign delivery to vehicles
            for line in rec.delivery_line_ids:
                line.vehicle_id.delivery_id = rec
