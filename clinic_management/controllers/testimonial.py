# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
import base64
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class ClinicTestimonialController(http.Controller):
    
    @http.route(['/clinic/testimonials'], type='http', auth='public', website=True)
    def testimonials(self, **kw):
        """Display patient testimonials"""
        testimonials = request.env['clinic.testimonial'].sudo().search([
            ('display_on_website', '=', True),
            ('active', '=', True)
        ], order='sequence, id desc')
        
        values = {
            'testimonials': testimonials,
            'page_name': 'testimonials',
        }
        return request.render('clinic_management.testimonials_page', values)
    
    @http.route(['/clinic/testimonial/submit'], type='http', auth='public', website=True, methods=['GET'])
    def testimonial_form(self, **kw):
        """Display testimonial submission form"""
        doctors = request.env['clinic.doctor'].sudo().search([('active', '=', True)])
        services = request.env['clinic.service'].sudo().search([('active', '=', True)])
        
        values = {
            'doctors': doctors,
            'services': services,
            'page_name': 'submit_testimonial',
        }
        return request.render('clinic_management.testimonial_submission_form', values)
    
    @http.route(['/clinic/testimonial/submit'], type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def testimonial_submit(self, **post):
        """Process testimonial submission"""
        try:
            # Validate required fields
            if not post.get('name') or not post.get('comment'):
                return request.render('website.http_error', {
                    'status_code': 400,
                    'status_message': 'Bad Request',
                    'error_message': 'Please fill in all required fields.'
                })
            
            # Prepare testimonial data
            testimonial_vals = {
                'name': post.get('name'),
                'comment': post.get('comment'),
                'rating': post.get('rating', '5'),
                'display_on_website': True,
                'date': fields.Date.today(),
            }
            
            # Optional fields
            if post.get('doctor_id'):
                testimonial_vals['doctor_id'] = int(post.get('doctor_id'))
            
            if post.get('service_id'):
                testimonial_vals['service_id'] = int(post.get('service_id'))
            
            # Handle image upload
            image_file = post.get('image')
            if image_file and hasattr(image_file, 'read'):
                testimonial_vals['image'] = base64.b64encode(image_file.read())
            
            # Create testimonial record
            request.env['clinic.testimonial'].sudo().create(testimonial_vals)
            
            # Return thank you page
            return request.render('clinic_management.testimonial_thank_you', {
                'page_name': 'testimonial_thank_you',
            })
            
        except Exception as e:
            _logger.exception("Error submitting testimonial: %s", str(e))
            return request.render('website.http_error', {
                'status_code': 500,
                'status_message': 'Internal Server Error',
                'error_message': 'An error occurred while processing your testimonial. Please try again.'
            })
