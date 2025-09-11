from odoo import models, fields, api, _
from odoo.exceptions import UserError

class IbcoShipment(models.Model):
    _name = "ibco.shipment"
    _description = "IBCO Shipment"
    _order = "id desc"

    name = fields.Char(string="Shipment Reference", required=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('ibco.shipment') or 'New')
    vessel = fields.Char(string="Vessel")
    arrival_date = fields.Date(string="Arrival Date")
    state = fields.Selection([('draft','Draft'),('validated','Validated'),('in_progress','In Progress'),('closed','Closed')], default='draft', string="Status")
    container_ids = fields.One2many('ibco.container','shipment_id', string="Containers")
    expense_ids = fields.One2many('ibco.expense','shipment_id', string="Expenses")
    damage_ids = fields.One2many('ibco.damage','shipment_id', string="Damages")
    delivery_ids = fields.One2many('ibco.delivery','shipment_id', string="Deliveries")

    # Commission fields (shipment level)
    commission_type = fields.Selection([('percent','Percentage'),('fixed','Fixed Amount')], default='percent', string="Commission Type")
    commission_value = fields.Float(string="Commission Value", help="Percentage (if percent) or Fixed amount (if fixed)")
    # Totals
    total_expense = fields.Monetary(string="Total Expenses", compute='_compute_totals', store=True, currency_field='company_currency_id')
    total_damage = fields.Monetary(string="Total Damage", compute='_compute_totals', store=True, currency_field='company_currency_id')
    total_revenue = fields.Monetary(string="Total Invoices Revenue", compute='_compute_totals', store=True, currency_field='company_currency_id')
    profit = fields.Monetary(string="Profit", compute='_compute_totals', store=True, currency_field='company_currency_id')
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', default=lambda self: self.env.company.currency_id)
    attachment_ids = fields.Many2many(
        'ir.attachment',           # Model for attachments
        'ibco_shipment_attachment_rel',  # Relation table name
        'shipment_id',             # Column for this model
        'attachment_id',           # Column for attachment model
        string='Attachments'
    )
    
    # Smart Button Fields
    delivery_count = fields.Integer(string='Delivery Count', compute='_compute_counts')
    order_count = fields.Integer(string='Order Count', compute='_compute_counts')
    invoice_count = fields.Integer(string='Invoice Count', compute='_compute_counts')

    @api.depends('expense_ids.amount','damage_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.total_expense = sum(rec.expense_ids.mapped('amount') or [])
            rec.total_damage = sum(rec.damage_ids.mapped('amount') or [])
            # revenue: sum invoices linked via deliveries' sale_order -> invoices. We'll compute naive: sum of invoice.amount_total for invoices linked
            invoices = self.env['account.move']
            for d in rec.delivery_ids:
                if d.invoice_id:
                    invoices |= d.invoice_id
            rec.total_revenue = sum(invoices.mapped('amount_total') or [])
            rec.profit = rec.total_revenue - (rec.total_expense + rec.total_damage)

    @api.depends('delivery_ids')    
    def _compute_counts(self):
        for rec in self:
            rec.delivery_count = len(rec.delivery_ids)
            
            # Count orders from deliveries
            orders = self.env['sale.order']
            for delivery in rec.delivery_ids:
                if delivery.sale_order_id:
                    orders |= delivery.sale_order_id
            rec.order_count = len(orders)
            
            # Count invoices from deliveries
            invoices = self.env['account.move']
            for delivery in rec.delivery_ids:
                if delivery.invoice_id:
                    invoices |= delivery.invoice_id
            rec.invoice_count = len(invoices)

    def action_validate(self):
        """Validate Shipment - Create Sale Orders for each Vehicle Line"""
        for rec in self:
            # Pre-validation checks
            if not rec.container_ids:
                raise UserError(_("Add at least one container before Validation"))
            
            # Check commission rate is filled
            if not rec.commission_value:
                raise UserError(_("Commission rate must be filled before validation"))
            
            # Check expense lines exist
            if not rec.expense_ids:
                raise UserError(_("Expense lines must be entered before validation"))
            
            # Check containers and vehicle lines exist
            vehicle_lines = self.env['ibco.vehicle.line']
            for container in rec.container_ids:
                vehicle_lines |= container.vehicle_ids
            
            if not vehicle_lines:
                raise UserError(_("Containers and Vehicle lines must be added before validation"))
            
            # Create "Shipment Service" product if it doesn't exist
            product = self.env['product.product'].search([('name', '=', 'Shipment Service')], limit=1)
            if not product:
                product = self.env['product.product'].create({
                    'name': 'Shipment Service',
                    'type': 'service',
                    'sale_ok': True,
                    'purchase_ok': False,
                    'list_price': 0.0,
                    'categ_id': self.env.ref('product.product_category_all').id,
                })
            
            # Group vehicles by customer to create consolidated sale orders
            vehicles_by_customer = {}
            for vehicle in vehicle_lines:
                if vehicle.customer_id:
                    customer_id = vehicle.customer_id.id
                    if customer_id not in vehicles_by_customer:
                        vehicles_by_customer[customer_id] = []
                    vehicles_by_customer[customer_id].append(vehicle)
            
            # Create Sale Order for each customer with multiple vehicle lines
            for customer_id, customer_vehicles in vehicles_by_customer.items():
                # Check if any vehicle already has a sale order
                existing_sale_orders = customer_vehicles[0].mapped('sale_line_id.order_id')
                if existing_sale_orders:
                    continue  # Skip if sale order already exists
                
                # Prepare order lines for all vehicles of this customer
                order_lines = []
                for vehicle in customer_vehicles:
                    # Build description with vehicle details
                    description = f"{rec.name} - {vehicle.chassis_no}"
                    if vehicle.make_model:
                        description += f" - {vehicle.make_model}"
                    if vehicle.year:
                        description += f" ({vehicle.year})"
                    if vehicle.color:
                        description += f" - {vehicle.color}"

                    line_vals = {
                        'product_id': product.id,
                        'name': description,
                        'product_uom_qty': 1,
                        'price_unit': vehicle.final_price,
                    }
                    order_lines.append((0, 0, line_vals))
                
                # Create consolidated Sale Order for this customer
                sale_order = self.env['sale.order'].create({
                    'partner_id': customer_id,
                    'state': 'draft',
                    'origin': rec.name,
                    'order_line': order_lines,
                })
                
                # Link each vehicle to its corresponding sale order line
                for i, vehicle in enumerate(customer_vehicles):
                    vehicle.sale_line_id = sale_order.order_line[i].id

            rec.state = 'validated'

    def action_set_in_progress(self):
        """Confirm Shipment - Auto-confirm Sale Orders and create Deliveries"""
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Shipment must be validated first"))
            
            # Get all vehicle lines with sale orders
            vehicle_lines = self.env['ibco.vehicle.line']
            for container in rec.container_ids:
                vehicle_lines |= container.vehicle_ids
            
            sale_orders = vehicle_lines.mapped('sale_line_id.order_id')
            
            # Auto-confirm all Sale Orders
            for sale_order in sale_orders:
                if sale_order.state == 'draft':
                    sale_order.action_confirm()
            
            # Create invoices for each unique sale order (avoiding duplicates)
            created_invoices = {}
            for sale_order in sale_orders:
                if sale_order.id not in created_invoices:
                    # Check if invoice already exists for this sale order
                    existing_invoices = self.env['account.move'].search([
                        ('invoice_origin', '=', sale_order.name),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ])
                    
                    if existing_invoices:
                        created_invoices[sale_order.id] = existing_invoices[0]
                    else:
                        # Create invoice from sale order
                        invoice_vals = sale_order._prepare_invoice()
                        invoice = self.env['account.move'].create(invoice_vals)
                        
                        # Create invoice lines
                        for line in sale_order.order_line:
                            line_vals = line._prepare_invoice_line()
                            line_vals['move_id'] = invoice.id
                            self.env['account.move.line'].create(line_vals)
                        
                        created_invoices[sale_order.id] = invoice
            
            # Create Delivery Records grouped by customer
            vehicles_by_customer = {}
            for vehicle in vehicle_lines:
                if vehicle.sale_line_id and not vehicle.delivery_id:
                    customer_id = vehicle.customer_id.id
                    if customer_id not in vehicles_by_customer:
                        vehicles_by_customer[customer_id] = {
                            'vehicles': [],
                            'sale_order': vehicle.sale_line_id.order_id,
                            'invoice': created_invoices.get(vehicle.sale_line_id.order_id.id)
                        }
                    vehicles_by_customer[customer_id]['vehicles'].append(vehicle)
            
            # Create delivery records for each customer
            for customer_id, customer_data in vehicles_by_customer.items():
                # Create Delivery Record
                delivery = self.env['ibco.delivery'].create({
                    'shipment_id': rec.id,
                    'customer_id': customer_id,
                    'sale_order_id': customer_data['sale_order'].id,
                    'invoice_id': customer_data['invoice'].id if customer_data['invoice'] else False,
                    'state': 'draft',
                })
                
                # Create delivery lines for each vehicle
                for vehicle in customer_data['vehicles']:
                    self.env['ibco.delivery.line'].create({
                        'delivery_id': delivery.id,
                        'container_id': vehicle.container_id.id,
                        'vehicle_id': vehicle.id,
                    })
                    
                    # Link delivery to vehicle
                    vehicle.delivery_id = delivery.id

            rec.state = 'in_progress'

    def action_view_deliveries(self):
        """Action to view all deliveries for this shipment"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Deliveries',
            'res_model': 'ibco.delivery',
            'view_mode': 'list,form',
            'domain': [('shipment_id', '=', self.id)],
            'context': {'default_shipment_id': self.id},
        }

    def action_view_orders(self):
        """Action to view all sale orders related to this shipment"""
        self.ensure_one()
        order_ids = []
        for delivery in self.delivery_ids:
            if delivery.sale_order_id:
                order_ids.append(delivery.sale_order_id.id)
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sale Orders',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', order_ids)],
        }

    def action_view_invoices(self):
        """Action to view all invoices related to this shipment"""
        self.ensure_one()
        invoice_ids = []
        for delivery in self.delivery_ids:
            if delivery.invoice_id:
                invoice_ids.append(delivery.invoice_id.id)
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
        }

    def action_close(self):
        """Close Shipment - Only possible when all deliveries are delivered and all invoices are paid"""
        for rec in self:
            # Check all deliveries are marked as "delivered"
            undelivered = rec.delivery_ids.filtered(lambda d: d.state != 'delivered')
            if undelivered:
                raise UserError(_("Cannot close: All deliveries must be marked as 'Delivered'. Pending deliveries: %s") % 
                              ', '.join(undelivered.mapped('name')))
            
            # Check all invoices are paid
            unpaid_invoices = self.env['account.move']
            for delivery in rec.delivery_ids:
                if delivery.invoice_id and delivery.invoice_id.payment_state != 'paid':
                    unpaid_invoices |= delivery.invoice_id
            
            if unpaid_invoices:
                raise UserError(_("Cannot close: All invoices must be paid. Unpaid invoices"))
            rec.state = 'closed'
