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
    shift_type = fields.Selection([('morning', 'Morning'), ('evening', 'Evening')], string="Shift Type")
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
        ('evening', 'Evening')
    ], string='Shift')
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
        weekday = str(today.weekday())  # 0 = Monday, 6 = Sunday
        
        # Current time as float
        now = datetime.datetime.now()
        current_time_float = now.hour + now.minute / 60
        
        # Find slots for today using new structure
        new_structure_slots = self.search([
            ('day_of_week', '=', weekday),
            ('status', 'in', ['available', 'booked'])
        ])
        
        slots_to_expire = []
        for slot in new_structure_slots:
            # Convert string time to float for comparison
            if slot.end_time:
                end_time_float = slot._string_to_float_time(slot.end_time)
                if end_time_float < current_time_float:
                    slots_to_expire.append(slot.id)
            elif slot.end_time_float and slot.end_time_float < current_time_float:
                slots_to_expire.append(slot.id)
        
        # Also check old structure for backward compatibility
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_name = day_names[today.weekday()]
        day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
        
        if day:
            old_structure_slots = self.search([
                ('day_id', '=', day.id),
                ('end_time_float', '<', current_time_float),
                ('status', 'in', ['available', 'booked'])
            ])
            slots_to_expire.extend(old_structure_slots.ids)
        
        # Mark as expired
        if slots_to_expire:
            slots_to_expire_records = self.browse(slots_to_expire)
            slots_to_expire_records.write({'status': 'expired'})
            
            # Handle no-shows for booked appointments
            for slot in slots_to_expire_records.filtered(lambda s: s.appointment_ids):
                for appointment in slot.appointment_ids.filtered(lambda a: a.state in ['confirmed']):
                    appointment.write({'state': 'no_show'})
