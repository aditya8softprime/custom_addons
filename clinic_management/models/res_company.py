# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    header_image = fields.Binary(
        string='Header Image',
        help='Header image for clinic prescriptions and documents'
    )
    footer_image = fields.Binary(
        string='Footer Image', 
        help='Footer image for clinic prescriptions and documents'
    )
    enable_queue_system = fields.Boolean(
        string='Enable Queue System',
        default=True,
        help='Enable automatic queue number generation for appointments based on doctor and date'
    )