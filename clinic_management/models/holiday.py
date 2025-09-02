from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta

class ClinicHoliday(models.Model):
    _name = 'clinic.holiday'
    _description = 'Doctor Leave/Holiday'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'from_date desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True, tracking=True)
    leave_type = fields.Selection([
        ('full_day', 'Full Day'),
        ('half_day', 'Half Day')
    ], string='Leave Type', default='full_day', required=True, tracking=True)
    from_date = fields.Date(string='From Date', required=True, tracking=True)
    to_date = fields.Date(string='To Date', required=True, tracking=True)
    reason = fields.Text(string='Reason')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.depends('doctor_id', 'from_date', 'to_date')
    def _compute_name(self):
        for record in self:
            if record.doctor_id and record.from_date:
                if record.from_date == record.to_date:
                    record.name = f"{record.doctor_id.name} - {record.from_date}"
                else:
                    record.name = f"{record.doctor_id.name} - {record.from_date} to {record.to_date}"
            else:
                record.name = 'New'

    @api.constrains('from_date', 'to_date')
    def _check_dates(self):
        for record in self:
            if record.from_date > record.to_date:
                raise ValidationError(_("End date cannot be before start date"))

    def action_approve(self):
        """Approve leave and block slots"""
        self.write({'state': 'approved'})
        self._block_slots()

    def action_cancel(self):
        """Cancel leave and unblock slots"""
        self.write({'state': 'cancelled'})
        self._unblock_slots()

    def _block_slots(self):
        """Block all slots in the leave period"""
        for holiday in self:
            current_date = holiday.from_date
            while current_date <= holiday.to_date:
                day_name = current_date.strftime('%A')
                day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
                if day:
                    # Block available slots for this doctor on this day
                    slots = self.env['clinic.slot'].search([
                        ('doctor_id', '=', holiday.doctor_id.id),
                        ('day_id', '=', day.id),
                        ('status', '=', 'available')
                    ])
                    slots.write({'status': 'blocked'})

                    # Cancel affected appointments
                    appointments = self.env['clinic.appointment'].search([
                        ('doctor_id', '=', holiday.doctor_id.id),
                        ('appointment_date', '=', current_date),
                        ('state', 'in', ['draft', 'confirmed'])
                    ])
                    appointments.write({
                        'state': 'cancelled',
                        'cancellation_reason': 'Doctor unavailable due to leave'
                    })
                current_date += timedelta(days=1)

    def _unblock_slots(self):
        """Unblock slots if leave is cancelled"""
        for holiday in self:
            current_date = holiday.from_date
            while current_date <= holiday.to_date:
                day_name = current_date.strftime('%A')
                day = self.env['clinic.days'].search([('name', '=', day_name)], limit=1)
                if day:
                    slots = self.env['clinic.slot'].search([
                        ('doctor_id', '=', holiday.doctor_id.id),
                        ('day_id', '=', day.id),
                        ('status', '=', 'blocked')
                    ])
                    slots.write({'status': 'available'})
                current_date += timedelta(days=1)

    @api.model
    def _cron_unblock_expired_leaves(self):
        """Cron job to unblock slots for expired leaves"""
        expired_leaves = self.search([
            ('to_date', '<', fields.Date.today()),
            ('state', '=', 'approved')
        ])
        for leave in expired_leaves:
            slots = self.env['clinic.slot'].search([
                ('doctor_id', '=', leave.doctor_id.id),
                ('status', '=', 'blocked')
            ])
            slots.write({'status': 'available'})
