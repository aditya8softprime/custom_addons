from odoo import models, fields, api

class ClinicWebsiteSettings(models.Model):
    _name = 'clinic.website.settings'
    _description = 'Clinic Website Settings'
    
    name = fields.Char(string='Name', default='Website Settings')
    
    # Clinic Information
    clinic_name = fields.Char(string='Clinic Name')
    clinic_tagline = fields.Char(string='Clinic Tagline')
    clinic_description = fields.Html(string='Clinic Description')
    
    # Contact Information
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    address = fields.Text(string='Address')
    
    # Social Media
    facebook_url = fields.Char(string='Facebook URL')
    twitter_url = fields.Char(string='Twitter URL')
    instagram_url = fields.Char(string='Instagram URL')
    linkedin_url = fields.Char(string='LinkedIn URL')
    
    # SEO
    meta_title = fields.Char(string='Meta Title')
    meta_description = fields.Text(string='Meta Description')
    meta_keywords = fields.Char(string='Meta Keywords')
    
    # Banners and Images
    banner_image = fields.Binary(string='Banner Image')
    logo_image = fields.Binary(string='Logo Image')
    
    # Booking Settings
    enable_online_booking = fields.Boolean(string='Enable Online Booking', default=True)
    booking_confirmation_message = fields.Html(string='Booking Confirmation Message')
    booking_email_template_id = fields.Many2one('mail.template', string='Booking Email Template')
    
    # Footer Information
    footer_text = fields.Html(string='Footer Text')
    copyright_text = fields.Char(string='Copyright Text')
    
    @api.model
    def get_settings(self):
        """Get the website settings or create default if not exists"""
        settings = self.search([], limit=1)
        if not settings:
            settings = self.create({
                'clinic_name': self.env.company.name,
                'clinic_tagline': 'Your Health is Our Priority',
                'enable_online_booking': True,
                'copyright_text': f'© {fields.Date.today().year} {self.env.company.name}. All Rights Reserved.'
            })
        return settings
