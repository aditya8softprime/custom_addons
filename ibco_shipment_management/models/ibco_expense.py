from odoo import models, fields, api

class IbcoExpense(models.Model):
    _name = "ibco.expense"
    _description = "IBCO Expense"

    name = fields.Char(string="Expense Name")
    expense_type = fields.Selection([
        ('freight','Freight'),
        ('port','Port Charges'),
        ('customs','Customs Duty'),
        ('handling','Handling'),
        ('other','Other')
    ], string='Expense Type', required=True)
    amount = fields.Monetary(string="Amount", required=True, currency_field='company_currency_id')
    shipment_id = fields.Many2one('ibco.shipment', string="Shipment", ondelete='cascade')
    container_id = fields.Many2one('ibco.container', string="Container", ondelete='cascade')
    date = fields.Date(string='Date')
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', default=lambda self: self.env.company.currency_id)
# -*- coding: utf-8 -*-
# IBCO Expense Model
