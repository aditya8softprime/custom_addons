from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClinicSlot(models.Model):
    _name = 'clinic.slot'
    _description = 'Clinic Appointment Slots'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'  # use our computed label everywhere

    # New structure fields
    doctor_id = fields.Many2one('clinic.doctor', string="Doctor", required=True, ondelete="cascade")
    shift_config_id = fields.Many2one('doctor.shift.config', string="Shift Config", ondelete="cascade")
    day_of_week = fields.Selection([
        ('0', 'Monday'), ('1', 'Tuesday'), ('2', 'Wednesday'),
        ('3', 'Thursday'), ('4', 'Friday'), ('5', 'Saturday'), ('6', 'Sunday')
    ], string="Day of Week")
    shift_type = fields.Selection([
        ('morning', 'Morning'),
        ('evening', 'Evening'),
        ('night', 'Night'),
    ], string="Shift Type")
    slot_label = fields.Char("Slot Label")
    start_time = fields.Char("Start Time")
    end_time = fields.Char("End Time")
    
    # Backward compatibility fields (kept for existing data)
    day_id = fields.Many2one('clinic.days', string='Day')  # Made optional for backward compatibility
    start_time_float = fields.Float(string='Start Time Float')  # Renamed for clarity
    end_time_float = fields.Float(string='End Time Float')      # Renamed for clarity
    duration = fields.Float(string='Duration (mins)')
    slot_number = fields.Char(string='Slot Number')
    shift = fields.Selection([
        ('morning', 'Morning'),
        ('evening', 'Evening'),
        ('night', 'Night'),
    ], string='Shift')
    # New simpler availability flags
    is_blocked = fields.Boolean(string='Blocked', default=False, help="If enabled, this slot template is not selectable for any date.")
    patients_count = fields.Integer(string='Appointments Count', compute='_compute_patients_count')


    
    appointment_ids = fields.One2many('clinic.appointment', 'slot_id', string='Appointments')
    
    color = fields.Integer(string='Color', compute='_compute_color')
    
    _sql_constraints = [
        ('slot_number_doctor_uniq', 'unique(slot_number, doctor_id)', 
         'Slot Number must be unique per doctor!')
    ]
    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('start_time', 'end_time', 'day_of_week', 'shift_type', 'slot_label', 
                 'start_time_float', 'end_time_float', 'day_id.name', 'shift')
    def _compute_display_name(self):
        def fmt(t):
            h = int(t or 0)
            m = int(round(((t or 0) - h) * 60))
            return f"{h:02d}:{m:02d}"

        for rec in self:
            # New structure - use slot_label if available
            if rec.slot_label and rec.day_of_week is not False:
                day_names = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
                day_code = day_names[int(rec.day_of_week)] if rec.day_of_week else ""
                shift_txt = dict(self._fields['shift_type'].selection).get(rec.shift_type, "") if rec.shift_type else ""
                
                parts = [p for p in [day_code, shift_txt, rec.slot_label] if p]
                rec.display_name = " ".join(parts) or "Slot"
                continue
                
            # Backward compatibility - use old structure
            day_code = (rec.day_id.name[:3].upper()) if rec.day_id and rec.day_id.name else ""
            shift_txt = dict(self._fields['shift'].selection).get(rec.shift, "") if rec.shift else ""

            # Use new string times or fall back to float times
            if rec.start_time and rec.end_time:
                time_txt = f"{rec.start_time} - {rec.end_time}"
            elif rec.start_time_float is not None and rec.end_time_float is not None:
                time_txt = f"{fmt(rec.start_time_float)} - {fmt(rec.end_time_float)}"
            else:
                time_txt = ""

            parts = [p for p in [day_code, shift_txt, time_txt] if p]
            rec.display_name = " ".join(parts) or "Slot"


    @api.depends('is_blocked')
    def _compute_color(self):
        """Set color based on blocked flag"""
        for slot in self:
            slot.color = 1 if slot.is_blocked else 10
    
    @api.depends('appointment_ids')
    def _compute_patients_count(self):
        """Compute total number of non-cancelled appointments linked to this slot (all dates)."""
        for slot in self:
            slot.patients_count = len(slot.appointment_ids.filtered(
                lambda a: a.state not in ['cancelled', 'no_show']
            ))
    
    @api.constrains('start_time_float', 'end_time_float')
    def _check_times(self):
        for slot in self:
            # Check float times (backward compatibility)
            if (slot.start_time_float is not None and slot.end_time_float is not None 
                and slot.start_time_float >= slot.end_time_float):
                raise ValidationError(_("End Time must be greater than Start Time"))

    def _float_time_convert(self, float_time):
        """Convert float time to formatted string (HH:MM)"""
        hours = int(float_time)
        minutes = int((float_time - hours) * 60)
        return f"{hours:02d}:{minutes:02d}"
    
    def _string_to_float_time(self, time_str):
        """Convert time string (HH:MM) to float"""
        if not time_str or ':' not in time_str:
            return 0.0
        try:
            hours, minutes = time_str.split(':')
            return float(hours) + float(minutes) / 60
        except (ValueError, AttributeError):
            return 0.0
    
    def action_toggle_block(self):
        """Toggle blocked flag for this slot template"""
        for slot in self:
            slot.is_blocked = not slot.is_blocked
    
    def action_cancel_appointments(self):
        """Cancel all non-completed appointments linked to this slot (any date)"""
        for slot in self:
            slot.appointment_ids.filtered(lambda a: a.state not in ['completed', 'cancelled']).write({
                'state': 'cancelled',
                'cancellation_reason': 'Slot template cancelled by clinic'
            })
    
    @api.model
    def _cron_mark_no_shows(self):
        """Cron job to mark today's past appointments as no_show based on their slot end time"""
        import datetime
        today = fields.Date.today()
        now = datetime.datetime.now()
        current_time_float = now.hour + now.minute / 60
        
        # Find today's appointments that are still in progress/confirmed
        App = self.env['clinic.appointment']
        appts = App.search([
            ('appointment_date', '=', today),
            ('state', 'in', ['confirmed', 'paid', 'waiting', 'patient_in', 'in_consultation'])
        ])
        for appt in appts:
            end_time_float = 0.0
            if appt.end_time_str:
                end_time_float = self._string_to_float_time(appt.end_time_str)
            elif appt.end_time is not None:
                end_time_float = appt.end_time
            elif appt.slot_id and appt.slot_id.end_time_float:
                end_time_float = appt.slot_id.end_time_float
            if end_time_float and end_time_float < current_time_float:
                appt.write({'state': 'no_show'})
