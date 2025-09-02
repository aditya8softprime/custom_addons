{
    'name': 'Clinic Management',
    'version': '18.0.1.0.0',
    'summary': 'Complete Healthcare & Clinic Management System',
    'description': """
        This module provides a complete clinic management system with:
        - Doctor Management: Track doctors, specializations, and schedules
        - Patient Management: Maintain patient records and medical history
        - Appointment Scheduling: Book, reschedule, and manage appointments
        - Prescription Management: Create and manage prescriptions with medications
        - Website Integration: Allow patients to book appointments online
        - Role-based Access Control: Different permissions for doctors, nurses, and staff
    """,
    'category': 'Healthcare',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'calendar',
        'website',
        'contacts',
        'stock',
        'sale',
        'hr',
        'account',
        'web',
        'product',
    ],
    'data': [
        # Security
        'security/clinic_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/days_master_data.xml',
        'data/sequence_data.xml',
        'data/website_menu_data.xml',
        'data/email_templates.xml',
        
        # Views
        'views/days_views.xml',
        'views/service_views.xml',
        'views/slot_views.xml',
        'views/doctor_views.xml',
        'views/patient_views.xml',
        'views/prescription_views.xml',
        'views/appointment_views.xml',
        'views/holiday_views.xml',
        'views/testimonial_views.xml',
        'views/clinic_website_settings_views.xml',
        'views/prescription_dashboard_actions.xml',
        
        # Wizards
        'wizard/reschedule_appointment_views.xml',
        
        # Website
        'views/clinic_website_config.xml',
        'views/clinic_website_templates.xml',
        'views/testimonial_website_templates.xml',
        'views/clinic_error_template.xml',
        
        # Menus (must be last)
        'menu/clinic_menus.xml',
    ],
    'demo': [
        'demo/demo_medicines.xml',
        'demo/demo_services.xml',
        'demo/demo_doctors.xml',
        'demo/demo_patients.xml',
        'demo/demo_slots.xml',
        # 'demo/demo_appointments.xml', 
        # 'demo/demo_holidays.xml',
        # 'demo/demo_testimonials.xml',
        # 'demo/demo_website_settings.xml',
        'demo/demo_system_config.xml',
    ],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'assets': {
        'web.assets_backend': [
            # Dashboard files
            'clinic_management/static/src/js/appointment_dashboard.js',
            'clinic_management/static/src/css/appointment_dashboard.css',
            'clinic_management/static/src/xml/appointment_dashboard_template.xml',
            'clinic_management/static/src/js/signature_widget.js',
            'clinic_management/static/src/xml/signature_widget.xml',
        ],

        'web.assets_frontend': [
            # Website JS
            'clinic_management/static/src/js/website/**/*',
            
            # Website SCSS
            'clinic_management/static/src/scss/booking.scss',
            'clinic_management/static/src/scss/website/**/*',
            
            # Website XML Templates
            'clinic_management/static/src/xml/website/**/*',
        ],
        
    },
    'sequence': 1,
}
