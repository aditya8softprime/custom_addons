from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AppointmentRescheduleWizard(models.TransientModel):
    _name = 'appointment.reschedule.wizard'
    _description = 'Reschedule Appointment Wizard'
    
    appointment_id = fields.Many2one('clinic.appointment', string='Appointment', required=True)
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True)
    service_id = fields.Many2one('clinic.service', string='Service', required=True)
    
    # Original appointment details (for reference)
    original_date = fields.Date(related='appointment_id.appointment_date', string='Original Date')
    original_slot_id = fields.Many2one(related='appointment_id.slot_id', string='Original Slot')
    
    # New appointment details
    new_date = fields.Date(string='New Date', required=True)
    new_slot_id = fields.Many2one('clinic.slot', string='New Slot', required=True,
                                 domain="[('doctor_id', '=', doctor_id), ('status', '=', 'available')]")
    reason = fields.Text(string='Reason for Reschedule')
    
    @api.model
    def default_get(self, fields_list):
        """Set default new_date from appointment's next_visit_date if available"""
        result = super().default_get(fields_list)
        
        # Get appointment from context
        appointment_id = self.env.context.get('default_appointment_id')
        if appointment_id:
            appointment = self.env['clinic.appointment'].browse(appointment_id)
            
            # Set new_date from next_visit_date if available and no default_new_date in context
            if appointment.next_visit_date and 'new_date' in fields_list and 'default_new_date' not in self.env.context:
                result['new_date'] = appointment.next_visit_date
                
        # Override with explicit default_new_date from context if provided
        if 'default_new_date' in self.env.context and 'new_date' in fields_list:
            result['new_date'] = self.env.context['default_new_date']
            
        return result
    
    @api.onchange('doctor_id', 'new_date')
    def _onchange_doctor_date(self):
        """When doctor or date changes, reset slot and filter available slots"""
        self.new_slot_id = False
        if not self.doctor_id or not self.new_date:
            return
        
        # Get day of the week
        weekday = self.new_date.weekday()  # 0 = Monday, 6 = Sunday
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_name = day_names[weekday]
        
        # Find corresponding day record
        day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
        
        if not day:
            return {
                'warning': {
                    'title': 'No Day Configuration',
                    'message': f"Could not find day configuration for {day_name}"
                }
            }
        
        # Check if doctor is available on this day
        if day not in self.doctor_id.available_days:
            return {
                'warning': {
                    'title': 'Doctor Not Available',
                    'message': f"Doctor {self.doctor_id.name} is not available on {day_name}"
                }
            }
        
        # Check if doctor is on leave
        holidays = self.env['clinic.holiday'].search([
            ('doctor_id', '=', self.doctor_id.id),
            ('state', '=', 'approved'),
            ('from_date', '<=', self.new_date),
            ('to_date', '>=', self.new_date)
        ])
        
        if holidays:
            return {
                'warning': {
                    'title': 'Doctor on Leave',
                    'message': f"Doctor {self.doctor_id.name} is on leave on {self.new_date}"
                }
            }
    
    def action_reschedule(self):
        """Reschedule the appointment"""
        self.ensure_one()
        
        if self.appointment_id.state in ['completed', 'no_show']:
            raise ValidationError(_("Cannot reschedule an appointment that is completed, cancelled, or marked as no-show"))
        
        # Check if new slot is available
        if self.new_slot_id.status != 'available':
            raise ValidationError(_("The selected slot is no longer available"))
        
        # Create new appointment
        new_appointment = self.env['clinic.appointment'].create({
            'patient_id': self.patient_id.id,
            'doctor_id': self.doctor_id.id,
            'slot_id': self.new_slot_id.id,
            'service_id': self.service_id.id,
            'appointment_date': self.new_date,
            'consulting_fee': self.appointment_id.consulting_fee,
            'symptom': self.appointment_id.symptom,
            'state': 'confirmed',
            'original_appointment_id': self.appointment_id.id,
        })
        
        # Update original appointment
        self.appointment_id.write({
            'state': 'rescheduled',
            'rescheduled_to_id': new_appointment.id,
            'cancellation_reason': self.reason or 'Rescheduled by user'
        })
        
        # Update slot statuses
        self.new_slot_id.status = 'booked'
        
        # If original slot is booked, make it available again
        if self.original_slot_id.status == 'booked':
            self.original_slot_id.status = 'available'
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rescheduled Appointment'),
            'res_model': 'clinic.appointment',
            'res_id': new_appointment.id,
            'view_mode': 'form',
            'target': 'current',
        }
