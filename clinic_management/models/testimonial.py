# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ClinicTestimonial(models.Model):
    _name = 'clinic.testimonial'
    _description = 'Clinic Patient Testimonial'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id desc'
    
    name = fields.Char(string='Patient Name', required=True)
    image = fields.Binary(string='Patient Image')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    # Changed from Selection to Float but kept compatibility with existing records
    rating = fields.Selection([
        ('1', '1 Star'),
        ('2', '2 Stars'),
        ('3', '3 Stars'),
        ('4', '4 Stars'),
        ('5', '5 Stars'),
    ], string='Rating', required=True, default='5')
    comment = fields.Text(string='Testimonial', required=True)
    service_id = fields.Many2one('clinic.service', string='Service Received')
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor')
    date = fields.Date(string='Date', default=fields.Date.context_today)
    display_on_website = fields.Boolean(string='Display on Website', default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    
    @api.model
    def get_website_testimonials(self):
        """Get testimonials for display on website"""
        return self.search([
            ('display_on_website', '=', True),
            ('active', '=', True),
            ('state', '=', 'published')
        ], order='sequence, id desc')
