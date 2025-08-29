from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClinicSlot(models.Model):
    _name = 'clinic.slot'
    _description = 'Clinic Appointment Slots'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True, ondelete='cascade')
    day_id = fields.Many2one('clinic.days', string='Day', required=True)
    start_time = fields.Float(string='Start Time', required=True)
    end_time = fields.Float(string='End Time', required=True)
    duration = fields.Float(string='Duration (mins)', required=True)
    slot_number = fields.Char(string='Slot Number', required=True)
    max_patients = fields.Integer(string='Max Patients', default=1)
    current_patients = fields.Integer(string='Current Patients', compute='_compute_current_patients')
    
    status = fields.Selection([
        ('available', 'Available'),
        ('booked', 'Booked'),
        ('blocked', 'Blocked'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired')
    ], string='Status', default='available', tracking=True)


    
    appointment_ids = fields.One2many('clinic.appointment', 'slot_id', string='Appointments')
    
    color = fields.Integer(string='Color', compute='_compute_color')
    
    _sql_constraints = [
        ('slot_number_doctor_uniq', 'unique(slot_number, doctor_id)', 
         'Slot Number must be unique per doctor!')
    ]
    
    def name_get(self):
        """Show 'Start - End (Day)' in Many2one dropdown"""
        result = []
        for rec in self:
            if rec.start_time is not None and rec.end_time is not None:
                start_hours = int(rec.start_time)
                start_minutes = int(round((rec.start_time % 1) * 60))
                end_hours = int(rec.end_time)
                end_minutes = int(round((rec.end_time % 1) * 60))

                start = "%02d:%02d" % (start_hours, start_minutes)
                end = "%02d:%02d" % (end_hours, end_minutes)
                name = f"{start} - {end} ({rec.day_id.name or ''})"
            else:
                name = rec.day_id.name or "Slot"

            result.append((rec.id, name))
        return result
        
    @api.depends('status')
    def _compute_color(self):
        """Set color based on status for kanban view"""
        for slot in self:
            if slot.status == 'available':
                slot.color = 10  # Green
            elif slot.status == 'booked':
                slot.color = 1   # Red
            elif slot.status == 'blocked':
                slot.color = 4   # Purple
            elif slot.status == 'cancelled':
                slot.color = 3   # Yellow
            else:
                slot.color = 0   # Grey
    
    @api.depends('appointment_ids')
    def _compute_current_patients(self):
        """Compute the number of patients currently booked in this slot"""
        for slot in self:
            slot.current_patients = len(slot.appointment_ids.filtered(
                lambda a: a.state not in ['cancelled', 'no_show']
            ))
    
    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for slot in self:
            if slot.start_time >= slot.end_time:
                raise ValidationError(_("End Time must be greater than Start Time"))
    
    @api.constrains('current_patients', 'max_patients')
    def _check_capacity(self):
        for slot in self:
            if slot.current_patients > slot.max_patients:
                raise ValidationError(_("Cannot exceed maximum patient capacity for this slot"))

    def _float_time_convert(self, float_time):
        """Convert float time to formatted string (HH:MM)"""
        hours = int(float_time)
        minutes = int((float_time - hours) * 60)
        return f"{hours:02d}:{minutes:02d}"
    
    def action_set_available(self):
        """Set slot status to Available"""
        self.write({'status': 'available'})
    
    def action_block(self):
        """Block slot from booking"""
        self.write({'status': 'blocked'})
    
    def action_cancel(self):
        """Cancel all appointments in this slot and mark as cancelled"""
        for slot in self:
            # Cancel related appointments
            slot.appointment_ids.filtered(lambda a: a.state not in ['completed', 'cancelled']).write({
                'state': 'cancelled',
                'cancellation_reason': 'Slot cancelled by clinic'
            })
            slot.status = 'cancelled'
    
    @api.model
    def _cron_expire_past_slots(self):
        """Cron job to mark past slots as expired"""
        import datetime
        today = fields.Date.today()
        weekday = today.weekday()  # 0 = Monday, 6 = Sunday
        
        # Map weekday to day name
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_name = day_names[weekday]
        
        # Find day record
        day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
        
        if not day:
            return
        
        # Current time as float
        now = datetime.datetime.now()
        current_time_float = now.hour + now.minute / 60
        
        # Expire slots for today that are in the past
        slots_to_expire = self.search([
            ('day_id', '=', day.id),
            ('end_time', '<', current_time_float),
            ('status', 'in', ['available', 'booked'])
        ])
        
        # Mark as expired
        slots_to_expire.write({'status': 'expired'})
        
        # Handle no-shows for booked appointments
        for slot in slots_to_expire.filtered(lambda s: s.appointment_ids):
            for appointment in slot.appointment_ids.filtered(lambda a: a.state in ['confirmed']):
                appointment.write({'state': 'no_show'})
