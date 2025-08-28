# -*- coding: utf-8 -*-

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    module_clinic_management = fields.Boolean(string="Clinic Management", 
                                          help="Enable clinic management features")
    clinic_allow_online_booking = fields.Boolean(string="Allow Online Booking", 
                                                default=True,
                                                config_parameter='clinic_management.allow_online_booking')
    clinic_booking_confirmation_email = fields.Boolean(string="Send Confirmation Email", 
                                                      default=True,
                                                      config_parameter='clinic_management.booking_confirmation_email')
