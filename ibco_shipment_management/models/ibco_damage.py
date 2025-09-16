from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class IbcoDamage(models.Model):
    _name = "ibco.damage"
    _description = "IBCO Damage Expense"
    _check_company_auto = True

    name = fields.Char(string="Damage Description")
    amount = fields.Float(string="Amount", required=True, digits=(16, 2))
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", ondelete='cascade', check_company=True)
    vehicle_id = fields.Many2one('ibco.vehicle.line', string="Vehicle/Cargo", ondelete='cascade',domain="[('shipment_id', '=', shipment_id)]")
    partner_id = fields.Many2one('res.partner', string="Vendor/Partner", help="Partner responsible for the damage")
    date = fields.Date(string='Date')
    expense_id = fields.Many2one('hr.expense', string="Related Expense", readonly=True)
    attachment_ids = fields.Many2many('ir.attachment', string="Attachments")

    def action_create_expense(self):
        """Create HR expense for this damage"""
        self.ensure_one()
        if self.expense_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Damage Expense',
                'res_model': 'hr.expense',
                'res_id': self.expense_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        product =self.env['product.product'].search([('default_code', '=', 'EXP_GEN')], limit=1)
        # Create new expense
        expense_vals = {
            'name': f"Damage: {self.name}",
            'employee_id': self.env.user.employee_id.id or self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1).id,
            'product_id': product.id,
            'vehicle_id': self.vehicle_id.id,
            'total_amount_currency': self.amount,
            'vendor_id': self.partner_id.id if self.partner_id else False,
            'shipment_id': self.shipment_id.id,
            'payment_mode': 'company_account',
            'description': f"Damage expense for vehicle {self.vehicle_id.chassis_no if self.vehicle_id else 'N/A'} - {self.name}",
        }
        
        expense = self.env['hr.expense'].create(expense_vals)
        self.expense_id = expense.id
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Damage Expense',
            'res_model': 'hr.expense',
            'res_id': expense.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.constrains('shipment_id', 'company_id')
    def _check_shipment_company(self):
        """Ensure damage company matches shipment company"""
        for rec in self:
            if rec.shipment_id and rec.shipment_id.company_id != rec.company_id:
                raise ValidationError(_("Damage company must match shipment company."))
        
