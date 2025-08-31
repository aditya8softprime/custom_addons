from odoo import models, fields, api

class ClinicWebsiteSettings(models.Model):
    _name = 'clinic.website.settings'
    _description = 'Clinic Website Settings'
    
    name = fields.Char(string='Name', default='Website Settings')
    
    # ===================
    # STEP 1: CLINIC INFO SETUP
    # ===================
    # Basic clinic information (auto-fetch from company)
    clinic_name = fields.Char(string='Clinic Name', help='Will be auto-filled from company details')
    clinic_logo = fields.Binary(string='Clinic Logo', help='Upload your clinic logo')
    address = fields.Text(string='Address', help='Complete clinic address')
    phone = fields.Char(string='Phone Number', help='Primary contact number')
    email = fields.Char(string='Email Address', help='Primary email address')
    website_url = fields.Char(string='Website URL', help='Official website URL')
    
    # Auto-fetch company details
    auto_fetch_company_details = fields.Boolean(string='Auto-fetch from Company', default=True, 
                                               help='Automatically fetch details from company settings')
    
    # ===================
    # STEP 2: THEME SELECTION
    # ===================
    theme_name = fields.Selection([
        ('medical_blue', 'Medical Blue - Professional & Trustworthy'),
        ('health_green', 'Health Green - Natural & Healing'),
        ('care_purple', 'Care Purple - Compassionate & Modern'),
        ('wellness_orange', 'Wellness Orange - Energetic & Warm'),
        ('trust_teal', 'Trust Teal - Calm & Reliable'),
        ('classic_red', 'Classic Red - Bold & Confident'),
        ('elegant_navy', 'Elegant Navy - Sophisticated & Professional'),
        ('custom', 'Custom Colors - Design Your Own'),
    ], string='Website Theme', default='medical_blue', required=True,
       help='Choose a predefined theme or create custom colors')
    
    # Primary color (main brand color)
    primary_color = fields.Char(string='Primary Color', default='#007bff', 
                               help='Main brand color used for buttons, links, and highlights')
    
    # Custom theme colors (visible when theme is 'custom')
    secondary_color = fields.Char(string='Secondary Color', default='#6c757d')
    accent_color = fields.Char(string='Accent Color', default='#28a745')
    text_color = fields.Char(string='Text Color', default='#333333')
    background_color = fields.Char(string='Background Color', default='#ffffff')
    header_bg_color = fields.Char(string='Header Background', default='#ffffff')
    footer_bg_color = fields.Char(string='Footer Background', default='#f8f9fa')
    
    # ===================
    # STEP 3: WEBSITE CONTENT INPUT
    # ===================
    # About Us Section
    about_us_title = fields.Char(string='About Us Title', default='About Us')
    about_us_content = fields.Html(string='About Us Content', help='Rich text content about your clinic')
    
    # Banner and Tagline
    banner_image = fields.Binary(string='Banner Image', help='Main banner image for homepage')
    tagline = fields.Char(string='Main Tagline', help='Main tagline displayed on banner')
    clinic_tagline = fields.Char(string='Clinic Tagline', help='Secondary tagline about your clinic')
    
    # Opening Hours
    show_opening_hours = fields.Boolean(string='Show Opening Hours', default=True)
    opening_hours_title = fields.Char(string='Opening Hours Title', default='Opening Hours')
    monday_hours = fields.Char(string='Monday', default='9:00 AM - 5:00 PM')
    tuesday_hours = fields.Char(string='Tuesday', default='9:00 AM - 5:00 PM')
    wednesday_hours = fields.Char(string='Wednesday', default='9:00 AM - 5:00 PM')
    thursday_hours = fields.Char(string='Thursday', default='9:00 AM - 5:00 PM')
    friday_hours = fields.Char(string='Friday', default='9:00 AM - 5:00 PM')
    saturday_hours = fields.Char(string='Saturday', default='9:00 AM - 1:00 PM')
    sunday_hours = fields.Char(string='Sunday', default='Closed')
    
    # Clinic Images Gallery (6 images)
    show_clinic_gallery = fields.Boolean(string='Show Clinic Gallery', default=True)
    clinic_images_title = fields.Char(string='Clinic Images Title', default='Our Clinic')
    clinic_image_1 = fields.Binary(string='Clinic Image 1')
    clinic_image_2 = fields.Binary(string='Clinic Image 2')
    clinic_image_3 = fields.Binary(string='Clinic Image 3')
    clinic_image_4 = fields.Binary(string='Clinic Image 4')
    clinic_image_5 = fields.Binary(string='Clinic Image 5')
    clinic_image_6 = fields.Binary(string='Clinic Image 6')
    
    # Treatment Images (4 images)
    show_treatment_gallery = fields.Boolean(string='Show Treatment Gallery', default=True)
    treatment_images_title = fields.Char(string='Treatment Images Title', default='Our Treatments')
    treatment_image_1 = fields.Binary(string='Treatment Image 1')
    treatment_image_2 = fields.Binary(string='Treatment Image 2')
    treatment_image_3 = fields.Binary(string='Treatment Image 3')
    treatment_image_4 = fields.Binary(string='Treatment Image 4')
    
    # Social Media Links
    show_social_media = fields.Boolean(string='Show Social Media', default=True)
    social_media_location = fields.Selection([
        ('header', 'Header'),
        ('footer', 'Footer'),
        ('both', 'Both Header and Footer')
    ], string='Social Media Location', default='footer')
    facebook_url = fields.Char(string='Facebook URL')
    instagram_url = fields.Char(string='Instagram URL')
    twitter_url = fields.Char(string='Twitter/X URL')
    linkedin_url = fields.Char(string='LinkedIn URL')
    youtube_url = fields.Char(string='YouTube URL')
    whatsapp_number = fields.Char(string='WhatsApp Number', help='Include country code (e.g., +91XXXXXXXXXX)')
    
    # Doctors Section (Auto-populated from Doctor Master)
    show_doctors_section = fields.Boolean(string='Show Doctors Section', default=True)
    doctors_section_title = fields.Char(string='Doctors Section Title', default='Our Doctors')
    doctors_section_subtitle = fields.Char(string='Doctors Section Subtitle')
    max_doctors_display = fields.Integer(string='Max Doctors to Display', default=8, 
                                        help='Maximum number of doctors to show on homepage')
    
    # Services Section (Auto-populated from Services Master)
    show_services_section = fields.Boolean(string='Show Services Section', default=True)
    services_section_title = fields.Char(string='Services Section Title', default='Our Services')
    services_section_subtitle = fields.Char(string='Services Section Subtitle')
    max_services_display = fields.Integer(string='Max Services to Display', default=8,
                                         help='Maximum number of services to show on homepage')
    
    # Testimonials Section
    show_testimonials = fields.Boolean(string='Show Testimonials', default=True)
    testimonials_title = fields.Char(string='Testimonials Title', default='What Our Patients Say')
    
    # Contact Form
    show_contact_form = fields.Boolean(string='Show Contact Form', default=True)
    contact_form_title = fields.Char(string='Contact Form Title', default='Get In Touch')
    
    # SEO and Meta Information
    meta_title = fields.Char(string='Meta Title')
    meta_description = fields.Text(string='Meta Description')
    meta_keywords = fields.Char(string='Meta Keywords')
    
    # Booking Settings
    enable_online_booking = fields.Boolean(string='Enable Online Booking', default=True)
    booking_section_title = fields.Char(string='Booking Section Title', default='Book Your Appointment')
    booking_confirmation_message = fields.Html(string='Booking Confirmation Message')
    booking_email_template_id = fields.Many2one('mail.template', string='Booking Email Template')
    
    # Footer Information
    footer_about = fields.Html(string='Footer About Section')
    footer_quick_links = fields.Html(string='Footer Quick Links')
    copyright_text = fields.Char(string='Copyright Text')
    
    # Emergency Contact
    emergency_phone = fields.Char(string='Emergency Phone', help='24/7 emergency contact number')
    show_emergency_contact = fields.Boolean(string='Show Emergency Contact', default=False)
    
    # ===================
    # METHODS
    # ===================
    
    def fetch_company_details(self):
        """Button method to fetch company details"""
        company = self.env.company
        self.write({
            'clinic_name': company.name,
            'address': f"{company.street or ''} {company.street2 or ''} {company.city or ''} {company.zip or ''}".strip(),
            'phone': company.phone,
            'email': company.email,
            'website_url': company.website,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Company details fetched successfully!',
                'type': 'success',
                'sticky': False,
            }
        }
    
    def get_theme_colors(self):
        """Get colors for the selected theme"""
        theme_colors = {
            'medical_blue': {
                'primary': '#007bff',
                'secondary': '#6c757d',
                'accent': '#28a745',
                'text': '#333333',
                'background': '#ffffff',
                'header_bg': '#ffffff',
                'footer_bg': '#f8f9fa'
            },
            'health_green': {
                'primary': '#28a745',
                'secondary': '#6c757d',
                'accent': '#007bff',
                'text': '#2d5016',
                'background': '#ffffff',
                'header_bg': '#f8fff8',
                'footer_bg': '#e8f5e8'
            },
            'care_purple': {
                'primary': '#6f42c1',
                'secondary': '#6c757d',
                'accent': '#e83e8c',
                'text': '#333333',
                'background': '#ffffff',
                'header_bg': '#faf8ff',
                'footer_bg': '#f0ebff'
            },
            'wellness_orange': {
                'primary': '#fd7e14',
                'secondary': '#6c757d',
                'accent': '#dc3545',
                'text': '#333333',
                'background': '#ffffff',
                'header_bg': '#fff8f0',
                'footer_bg': '#ffebdb'
            },
            'trust_teal': {
                'primary': '#20c997',
                'secondary': '#6c757d',
                'accent': '#17a2b8',
                'text': '#0c5460',
                'background': '#ffffff',
                'header_bg': '#f0fcfa',
                'footer_bg': '#d1ecf1'
            },
            'classic_red': {
                'primary': '#dc3545',
                'secondary': '#6c757d',
                'accent': '#ffc107',
                'text': '#721c24',
                'background': '#ffffff',
                'header_bg': '#fff5f5',
                'footer_bg': '#f8d7da'
            },
            'elegant_navy': {
                'primary': '#002f5f',
                'secondary': '#6c757d',
                'accent': '#17a2b8',
                'text': '#1a1a1a',
                'background': '#ffffff',
                'header_bg': '#f0f4f8',
                'footer_bg': '#e7f1ff'
            }
        }
        
        if self.theme_name == 'custom':
            return {
                'primary': self.primary_color,
                'secondary': self.secondary_color,
                'accent': self.accent_color,
                'text': self.text_color,
                'background': self.background_color,
                'header_bg': self.header_bg_color,
                'footer_bg': self.footer_bg_color
            }
        else:
            return theme_colors.get(self.theme_name, theme_colors['medical_blue'])
    
    @api.onchange('theme_name')
    def _onchange_theme_name(self):
        """Update colors when theme changes"""
        if self.theme_name != 'custom':
            colors = self.get_theme_colors()
            self.primary_color = colors['primary']
            self.secondary_color = colors['secondary']
            self.accent_color = colors['accent']
            self.text_color = colors['text']
            self.background_color = colors['background']
            self.header_bg_color = colors['header_bg']
            self.footer_bg_color = colors['footer_bg']
    
    @api.onchange('auto_fetch_company_details')
    def _onchange_auto_fetch_company_details(self):
        """Fetch company details when option is enabled"""
        if self.auto_fetch_company_details:
            company = self.env.company
            self.clinic_name = company.name
            self.address = f"{company.street or ''} {company.street2 or ''} {company.city or ''} {company.zip or ''}".strip()
            self.phone = company.phone
            self.email = company.email
            self.website_url = company.website

    @api.model
    def get_settings(self):
        """Get the first available website settings record or create one"""
        settings = self.search([], limit=1)
        if not settings:
            # Create default settings
            settings = self.create({
                'name': 'Website Settings',
                'clinic_name': self.env.company.name or 'Your Clinic Name',
                'theme_name': 'medical_blue',
                'primary_color': '#007bff',
            })
        return settings

    @api.model
    def create(self, vals_list):
        """Auto-fetch company details when creating new settings"""
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
        
        for vals in vals_list:
            if vals.get('auto_fetch_company_details', True):
                company = self.env.company
                if not vals.get('clinic_name'):
                    vals['clinic_name'] = company.name
                if not vals.get('address'):
                    vals['address'] = f"{company.street or ''} {company.street2 or ''} {company.city or ''} {company.zip or ''}".strip()
                if not vals.get('phone'):
                    vals['phone'] = company.phone
                if not vals.get('email'):
                    vals['email'] = company.email
                if not vals.get('website_url'):
                    vals['website_url'] = company.website
        
        return super().create(vals_list)
