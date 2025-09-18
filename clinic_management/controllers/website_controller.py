from odoo import http
from odoo.http import request
import json


class ClinicWebsiteController(http.Controller):
    
    @http.route('/clinic/patient/lookup', type='json', auth='public', methods=['POST'], csrf=False)
    def patient_lookup(self, phone):
        """Lookup patient by phone number for auto-fill"""
        try:
            Patient = request.env['clinic.patient'].sudo()
            result = Patient.get_patient_by_phone(phone)
            return result
        except Exception as e:
            return {'exists': False, 'error': str(e)}