from odoo import http, fields, _
from odoo.http import request
from datetime import datetime, timedelta
import logging
import json
import base64

_logger = logging.getLogger(__name__)

class ClinicWebsite(http.Controller):
    
    def _get_clinic_settings(self):
        """Get clinic website settings"""
        settings = request.env['clinic.website.settings'].sudo().get_settings()
        return settings
    
    @http.route(['/clinic'], type='http', auth='public', website=True)
    def clinic_home(self, **kw):
        """Render the clinic homepage with all required data"""
        services = request.env['clinic.service'].sudo().search([('active', '=', True)])
        doctors = request.env['clinic.doctor'].sudo().search([('active', '=', True)])
        clinic_settings = self._get_clinic_settings()
        
        # Fetch testimonials for the homepage
        testimonials = request.env['clinic.testimonial'].sudo().search([
            ('state', '=', 'published')
        ], order='date desc, id desc')
        
        values = {
            'services': services,
            'doctors': doctors,
            'testimonials': testimonials,
            'clinic_settings': clinic_settings,
            'page_name': 'clinic_home',
        }
        return request.render('clinic_management.clinic_homepage', values)
    
    @http.route(['/clinic/doctor/<model("clinic.doctor"):doctor>'], type='http', auth='public', website=True)
    def doctor_detail(self, doctor, **kw):
        """Doctor detail page with specializations and available slots"""
        if not doctor.exists() or not doctor.active:
            return request.redirect('/clinic')
        
        clinic_settings = self._get_clinic_settings()
        
        # Prepare doctor data for JavaScript
        doctor_data = {
            'id': doctor.id,
            'name': doctor.name,
            'specialization_ids': [(spec.id, spec.name) for spec in doctor.specialization_ids] if doctor.specialization_ids else [],
            'qualification': doctor.qualification or '',
            'bio': doctor.bio or '',
            'consultation_fee': doctor.consultation_fee,
            'currency_id': doctor.currency_id.id,
            'currency_symbol': doctor.currency_id.symbol,
        }
            
        return request.render('clinic_management.doctor_detail', {
            'doctor': doctor,
            'clinic_settings': clinic_settings,
            'doctor_data_json': json.dumps(doctor_data),
            'page_name': 'doctor_profile',
        })
    
    @http.route(['/clinic/services'], type='http', auth='public', website=True)
    def services(self, **kw):
        """Display all available services/treatments"""
        services = request.env['clinic.service'].sudo().search([('active', '=', True)])
        clinic_settings = self._get_clinic_settings()
        
        # Prepare services data for JavaScript
        services_data = []
        for service in services:
            services_data.append({
                'id': service.id,
                'name': service.name,
                'description': service.description or '',
            })
            
        return request.render('clinic_management.services_page', {
            'services': services,
            'clinic_settings': clinic_settings,
            'services_data_json': json.dumps(services_data),
            'page_name': 'clinic_services',
        })

    @http.route(['/clinic/service/<model("clinic.service"):service>'], type='http', auth='public', website=True)
    def service_detail(self, service, **kw):
        """Individual service detail page"""
        if not service.exists() or not service.active:
            return request.redirect('/clinic/services')
        
        clinic_settings = self._get_clinic_settings()
        
        # Get doctors who offer this service
        doctors = request.env['clinic.doctor'].sudo().search([
            ('specialization_ids', 'in', service.id),
            ('active', '=', True)
        ])
        
        return request.render('clinic_management.service_detail', {
            'service': service,
            'doctors': doctors,
            'clinic_settings': clinic_settings,
            'page_name': 'service_detail',
        })
    
    @http.route(['/clinic/booking'], type='http', auth='public', website=True)
    def booking_form(self, **kw):
        """Display the appointment booking form"""
        services = request.env['clinic.service'].sudo().search([('active', '=', True)])
        clinic_settings = self._get_clinic_settings()
        return request.render('clinic_management.booking_form', {
            'services': services,
            'clinic_settings': clinic_settings,
            'page_name': 'booking_form',
            'datetime': datetime,
        })
    
    @http.route(['/clinic/booking/doctors'], type='json', auth='public', website=True)
    def get_doctors_for_service(self, service_id, **kw):
        """AJAX endpoint to get doctors who offer a specific service"""
        try:
            _logger.info(f"Getting doctors for service_id: {service_id}")
            
            if not service_id:
                return []
            
            # Find doctors who have this service in their specializations
            doctors = request.env['clinic.doctor'].sudo().search([
                ('specialization_ids', 'in', int(service_id)),
                ('active', '=', True)
            ])
            
            doctor_list = []
            for doctor in doctors:
                specializations = ', '.join(doctor.specialization_ids.mapped('name'))
                doctor_list.append({
                    'id': doctor.id,
                    'name': doctor.name,
                    'specializations': specializations,
                })
            
            _logger.info(f"Found {len(doctor_list)} doctors for service {service_id}")
            return doctor_list
            
        except Exception as e:
            _logger.exception("Error getting doctors for service: %s", str(e))
            return []
    
    @http.route(['/clinic/booking/slots'], type='json', auth='public', website=True)
    def get_available_slots(self, doctor_id, date_str, **kw):
        """AJAX endpoint to get available slots for a doctor on a specific date"""
        try:
            _logger.info(f"Getting slots for doctor_id: {doctor_id}, date: {date_str}")
            
            if not doctor_id or not date_str:
                return []
            
            # Convert date string to date object
            booking_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Get day of week (Monday=0, Sunday=6)
            day_index = booking_date.weekday()
            
            # Map day index to day names
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_name = day_names[day_index]
            
            # Find the day record
            day_record = request.env['clinic.days'].sudo().search([('name', '=', day_name)], limit=1)
            
            if not day_record:
                _logger.warning(f"Day record not found for {day_name}")
                return []
            
            # Get available slots for this doctor and day
            available_slots = request.env['clinic.slot'].sudo().search([
                ('doctor_id', '=', int(doctor_id)),
                ('day_id', '=', day_record.id),
                ('status', '=', 'available')
            ], order='start_time')
            
            # Format slots for the dropdown
            slots_data = []
            for slot in available_slots:
                # Convert float time to HH:MM format
                start_hour = int(slot.start_time)
                start_min = int((slot.start_time - start_hour) * 60)
                end_hour = int(slot.end_time)
                end_min = int((slot.end_time - end_hour) * 60)
                
                start_time_str = f"{start_hour:02d}:{start_min:02d}"
                end_time_str = f"{end_hour:02d}:{end_min:02d}"
                
                slots_data.append({
                    'id': slot.id,
                    'start_time': start_time_str,
                    'end_time': end_time_str,
                    'slot_number': slot.slot_number
                })
            
            _logger.info(f"Found {len(slots_data)} available slots")
            return slots_data
            
        except Exception as e:
            _logger.exception(f"Error in get_available_slots: {str(e)}")
            return []    
            
    @http.route(['/clinic/booking/submit'], type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def submit_booking(self, **post):
        """Process the appointment booking form submission"""
        try:
            # Log all submitted form data (except sensitive information)
            _logger.info("Booking form submitted with data: %s", {k: v for k, v in post.items() if k not in ['csrf_token']})
            
            # Validate required fields
            required_fields = ['patient_name', 'gender', 'age', 'phone', 'service_id', 'doctor_id', 'appointment_date', 'symptom']
            missing_fields = []
            
            for field in required_fields:
                if not post.get(field):
                    missing_fields.append(field)
            
            # Return error response if validation fails
            if missing_fields:
                _logger.warning(f"Validation failed. Missing fields: {missing_fields}")
                return request.render('clinic_management.booking_form', {
                    'services': request.env['clinic.service'].sudo().search([('active', '=', True)]),
                    'error_message': 'Please fill in all required fields.',
                    'form_data': post
                })
            
            # Extract form data
            patient_data = {
                'name': post.get('patient_name'),
                'gender': post.get('gender'),
                'age': int(post.get('age')),
                'phone': post.get('phone'),
                'email': post.get('email') or False,
            }
            
            # Check if patient already exists
            existing_patient = request.env['clinic.patient'].sudo().search([
                ('phone', '=', patient_data['phone'])
            ], limit=1)
            
            if existing_patient:
                patient = existing_patient
                # Update patient info if needed
                patient.sudo().write(patient_data)
            else:
                # Create new patient
                patient = request.env['clinic.patient'].sudo().create(patient_data)
            
            # Create appointment
            service_id = int(post.get('service_id'))
            doctor_id = int(post.get('doctor_id'))
            appointment_date = post.get('appointment_date')
            
            doctor = request.env['clinic.doctor'].sudo().browse(doctor_id)
            
            appointment_vals = {
                'patient_id': patient.id,
                'service_id': service_id,
                'doctor_id': doctor.id,
                'appointment_date': appointment_date,
                'consulting_fee': doctor.consultation_fee,
                'currency_id': doctor.currency_id.id,
                'symptom': post.get('symptom') or False,
                'state': 'confirm',
            }
            
            # Handle slot if provided
            slot_id = post.get('slot_id')
            if slot_id:
                try:
                    slot_id = int(slot_id)
                    slot = request.env['clinic.slot'].sudo().browse(slot_id)
                    
                    if slot.exists() and slot.status == 'available':
                        appointment_vals.update({
                            'slot_id': slot.id,
                            'start_time': slot.start_time,
                            'end_time': slot.end_time,
                        })
                        
                        # Create appointment
                        appointment = request.env['clinic.appointment'].sudo().create(appointment_vals)
                        
                        # Mark slot as booked
                        slot.sudo().write({
                            'status': 'booked'
                        })
                    else:
                        return request.render('clinic_management.booking_form', {
                            'services': request.env['clinic.service'].sudo().search([('active', '=', True)]),
                            'error_message': 'Selected time slot is no longer available.',
                            'form_data': post
                        })
                except (ValueError, TypeError):
                    # Invalid slot_id, proceed with simple appointment
                    appointment = request.env['clinic.appointment'].sudo().create(appointment_vals)
            else:
                # Simple appointment without slots
                appointment = request.env['clinic.appointment'].sudo().create(appointment_vals)
            
            # Confirm appointment
            if hasattr(appointment, 'action_confirm'):
                appointment.sudo().action_confirm()
            
            # Return success page
            clinic_settings = self._get_clinic_settings()
            return request.render('clinic_management.booking_confirmation', {
                'appointment': appointment,
                'clinic_settings': clinic_settings,
                'page_name': 'booking_confirmation',
            })
            
        except Exception as e:
            _logger.exception("Error during booking submission: %s", str(e))
            return request.render('clinic_management.booking_form', {
                'services': request.env['clinic.service'].sudo().search([('active', '=', True)]),
                'error_message': 'An error occurred while processing your booking. Please try again.',
                'form_data': post
            })
    
    @http.route(['/clinic/testimonials'], type='http', auth='public', website=True)
    def testimonials(self, **kw):
        """Display all published testimonials"""
        testimonials = request.env['clinic.testimonial'].sudo().search([
            ('state', '=', 'published')
        ], order='date desc, id desc')
        
        return request.render('clinic_management.testimonials_page', {
            'testimonials': testimonials,
            'page_name': 'testimonials',
        })
    
    @http.route(['/clinic/booking/confirmation/<model("clinic.appointment"):appointment>'], type='http', auth='public', website=True)
    def booking_confirmation_detail(self, appointment, **kw):
        """Display detailed booking confirmation"""
        if not appointment.exists():
            return request.redirect('/clinic')
        
        clinic_settings = self._get_clinic_settings()
        return request.render('clinic_management.booking_confirmation', {
            'appointment': appointment,
            'clinic_settings': clinic_settings,
            'page_name': 'booking_confirmation',
        })
    
    @http.route(['/clinic/testimonial/submit'], type='http', auth='public', website=True, methods=['GET', 'POST'], csrf=True)
    def testimonial_form(self, **post):
        """Display and process testimonial submission form"""
        if request.httprequest.method == 'POST':
            try:
                # Process form submission
                vals = {
                    'name': post.get('name'),
                    'rating': post.get('rating', '5'),  # Now a selection field that uses string values
                    'comment': post.get('comment'),
                    'date': fields.Date.today(),
                    'state': 'draft',  # Draft by default, admin will publish
                    'display_on_website': True,
                }
                
                # Optional fields
                if post.get('doctor_id'):
                    vals['doctor_id'] = int(post.get('doctor_id'))
                
                if post.get('service_id'):
                    vals['service_id'] = int(post.get('service_id'))
                
                # Handle image upload
                if 'image' in request.httprequest.files:
                    image_file = request.httprequest.files.get('image')
                    if image_file and image_file.filename:
                        image_data = image_file.read()
                        if image_data:
                            vals['image'] = base64.b64encode(image_data)
                
                # Create testimonial
                request.env['clinic.testimonial'].sudo().create(vals)
                
                # Redirect to thank you page
                return request.render('clinic_management.testimonial_thank_you', {
                    'page_name': 'testimonial_thank_you',
                })
                
            except Exception as e:
                _logger.exception("Error during testimonial submission: %s", str(e))
                return request.render('clinic_management.clinic_http_error', {
                    'status_code': 500,
                    'status_message': 'Internal Server Error',
                    'error_message': 'An error occurred while processing your testimonial. Please try again.'
                })
        
        # GET request - show the form
        doctors = request.env['clinic.doctor'].sudo().search([('active', '=', True)])
        services = request.env['clinic.service'].sudo().search([('active', '=', True)])
        
        return request.render('clinic_management.testimonial_submission_form', {
            'doctors': doctors,
            'services': services,
            'page_name': 'testimonial_submission',
        })
    
    @http.route(['/clinic/doctors'], type='http', auth='public', website=True)
    def doctors_list(self, **kw):
        """Display all doctors"""
        doctors = request.env['clinic.doctor'].sudo().search([('active', '=', True)])
        specializations = request.env['clinic.specialization'].sudo().search([])
        clinic_settings = self._get_clinic_settings()
        
        return request.render('clinic_management.doctors_page', {
            'doctors': doctors,
            'specializations': specializations,
            'clinic_settings': clinic_settings,
            'page_name': 'doctors_list',
        })
    
    @http.route(['/clinic/about'], type='http', auth='public', website=True)
    def about_us(self, **kw):
        """About us page"""
        clinic_settings = self._get_clinic_settings()
        
        return request.render('clinic_management.clinic_about', {
            'clinic_settings': clinic_settings,
            'page_name': 'about_us',
        })
    
    @http.route(['/clinic/contact'], type='http', auth='public', website=True)
    def contact_us(self, **kw):
        """Contact us page"""
        clinic_settings = self._get_clinic_settings()
        
        return request.render('clinic_management.clinic_contact', {
            'clinic_settings': clinic_settings,
            'page_name': 'contact_us',
        })
    
    @http.route(['/clinic/contact/submit'], type='http', auth='public', methods=['POST'], website=True)
    def contact_submit(self, **post):
        """Process contact form submission"""
        try:
            name = post.get('name', '').strip()
            email = post.get('email', '').strip()
            phone = post.get('phone', '').strip()
            message = post.get('message', '').strip()
            
            if not all([name, email, message]):
                return request.render('clinic_management.clinic_contact', {
                    'error_message': 'Please fill in all required fields.',
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'message': message,
                })
            
            # Create contact record (you would need a contact model)
            # For now, just return success
            return request.render('clinic_management.clinic_contact', {
                'success_message': 'Thank you for your message. We will get back to you soon!',
            })
            
        except Exception as e:
            _logger.exception("Error during contact form submission: %s", str(e))
            return request.render('clinic_management.clinic_contact', {
                'error_message': 'An error occurred while sending your message. Please try again.',
            })
            
    @http.route(['/clinic/*'], type='http', auth='public', website=True)
    def clinic_catch_all(self, **kw):
        """Catch-all route for clinic routes that don't exist"""
        return request.render('clinic_management.clinic_http_error', {
            'status_code': 404,
            'status_message': 'Page Not Found',
            'error_message': 'The requested page could not be found. Please use the navigation menu or return to the homepage.'
        })
