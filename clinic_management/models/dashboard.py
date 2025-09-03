# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, date, timedelta
from odoo.exceptions import AccessError


class ClinicDashboard(models.Model):
    _name = 'clinic.dashboard'
    _description = 'Clinic Dashboard Data Provider'

    @api.model
    def get_receptionist_dashboard_data(self):
        """Get dashboard data for receptionist role"""
        if not self.env.user.has_group('clinic_management.group_clinic_receptionist'):
            raise AccessError("Access Denied: Receptionist permissions required")
        
        today = date.today()
        
        # Today's appointments
        today_appointments = self.env['clinic.appointment'].search([
            ('appointment_date', '=', today)
        ])
        
        # Pending appointments (Draft/Waiting)
        pending_appointments = self.env['clinic.appointment'].search([
            ('state', 'in', ['draft', 'waiting'])
        ])
        
        # Doctor schedules for today
        doctor_schedules = self.env['clinic.slot'].search([
            ('day_master_id.name', '=', today.strftime('%A'))
        ])
        
        return {
            'today_appointments': {
                'count': len(today_appointments),
                'data': [{
                    'id': apt.id,
                    'patient_name': apt.patient_id.name,
                    'doctor_name': apt.doctor_id.name,
                    'service_name': apt.service_id.name,
                    'appointment_time': apt.appointment_time,
                    'state': apt.state,
                } for apt in today_appointments]
            },
            'pending_appointments': {
                'count': len(pending_appointments),
                'data': [{
                    'id': apt.id,
                    'patient_name': apt.patient_id.name,
                    'doctor_name': apt.doctor_id.name,
                    'service_name': apt.service_id.name,
                    'appointment_date': apt.appointment_date,
                    'appointment_time': apt.appointment_time,
                    'state': apt.state,
                } for apt in pending_appointments]
            },
            'doctor_schedules': {
                'count': len(doctor_schedules),
                'data': [{
                    'doctor_name': slot.doctor_id.name,
                    'start_time': slot.start_time,
                    'end_time': slot.end_time,
                    'day': slot.day_master_id.name,
                } for slot in doctor_schedules]
            }
        }

    @api.model
    def get_doctor_dashboard_data(self):
        """Get dashboard data for doctor role"""
        if not self.env.user.has_group('clinic_management.group_clinic_doctor'):
            raise AccessError("Access Denied: Doctor permissions required")
        
        today = date.today()
        
        # Get current doctor
        doctor = self.env['clinic.doctor'].search([
            ('user_id', '=', self.env.user.id)
        ], limit=1)
        
        if not doctor:
            return {'error': 'No doctor profile found for current user'}
        
        # Today's patients for this doctor
        today_appointments = self.env['clinic.appointment'].search([
            ('appointment_date', '=', today),
            ('doctor_id', '=', doctor.id)
        ])
        
        # Doctor's schedule
        doctor_slots = self.env['clinic.slot'].search([
            ('doctor_id', '=', doctor.id),
            ('day_master_id.name', '=', today.strftime('%A'))
        ])
        
        # Missed/Unattended patients
        missed_appointments = self.env['clinic.appointment'].search([
            ('doctor_id', '=', doctor.id),
            ('state', '=', 'missed'),
            ('appointment_date', '>=', today - timedelta(days=7))
        ])
        
        return {
            'doctor_info': {
                'name': doctor.name,
                'specialization': doctor.specialization,
                'id': doctor.id
            },
            'today_patients': {
                'count': len(today_appointments),
                'data': [{
                    'id': apt.id,
                    'patient_name': apt.patient_id.name,
                    'patient_age': apt.patient_id.age if apt.patient_id.age else 'N/A',
                    'service_name': apt.service_id.name,
                    'appointment_time': apt.appointment_time,
                    'state': apt.state,
                } for apt in today_appointments]
            },
            'doctor_schedule': {
                'count': len(doctor_slots),
                'data': [{
                    'start_time': slot.start_time,
                    'end_time': slot.end_time,
                    'day': slot.day_master_id.name,
                } for slot in doctor_slots]
            },
            'missed_patients': {
                'count': len(missed_appointments),
                'data': [{
                    'id': apt.id,
                    'patient_name': apt.patient_id.name,
                    'appointment_date': apt.appointment_date,
                    'appointment_time': apt.appointment_time,
                } for apt in missed_appointments]
            }
        }

    @api.model
    def get_admin_dashboard_data(self):
        """Get dashboard data for admin role"""
        if not self.env.user.has_group('clinic_management.group_clinic_admin'):
            raise AccessError("Access Denied: Admin permissions required")
        
        today = date.today()
        current_month_start = today.replace(day=1)
        
        # Appointments summary
        all_appointments = self.env['clinic.appointment'].search([])
        appointments_by_status = {}
        for state in ['draft', 'waiting', 'confirmed', 'completed', 'cancelled', 'missed']:
            appointments_by_status[state] = len(all_appointments.filtered(lambda x: x.state == state))
        
        # Revenue overview (current month)
        current_month_appointments = self.env['clinic.appointment'].search([
            ('appointment_date', '>=', current_month_start),
            ('appointment_date', '<=', today),
            ('state', '=', 'completed')
        ])
        
        revenue_by_service = {}
        revenue_by_doctor = {}
        total_revenue = 0
        
        for apt in current_month_appointments:
            service_name = apt.service_id.name
            doctor_name = apt.doctor_id.name
            service_fee = apt.service_id.fee or 0
            
            revenue_by_service[service_name] = revenue_by_service.get(service_name, 0) + service_fee
            revenue_by_doctor[doctor_name] = revenue_by_doctor.get(doctor_name, 0) + service_fee
            total_revenue += service_fee
        
        # Doctor utilization
        doctors = self.env['clinic.doctor'].search([])
        doctor_utilization = []
        
        for doctor in doctors:
            total_slots = len(self.env['clinic.slot'].search([('doctor_id', '=', doctor.id)]))
            booked_slots = len(current_month_appointments.filtered(lambda x: x.doctor_id.id == doctor.id))
            utilization = (booked_slots / total_slots * 100) if total_slots > 0 else 0
            
            doctor_utilization.append({
                'doctor_name': doctor.name,
                'utilization_percent': round(utilization, 2),
                'booked_slots': booked_slots,
                'total_slots': total_slots
            })
        
        # Upcoming doctor leaves
        upcoming_leaves = self.env['clinic.holiday'].search([
            ('start_date', '>=', today),
            ('start_date', '<=', today + timedelta(days=30))
        ])
        
        # Service popularity
        service_bookings = {}
        for apt in all_appointments:
            service_name = apt.service_id.name
            service_bookings[service_name] = service_bookings.get(service_name, 0) + 1
        
        return {
            'appointments_summary': {
                'total': len(all_appointments),
                'by_status': appointments_by_status
            },
            'revenue_overview': {
                'total_revenue': total_revenue,
                'by_service': revenue_by_service,
                'by_doctor': revenue_by_doctor,
                'period': f"{current_month_start.strftime('%B %Y')}"
            },
            'doctor_utilization': doctor_utilization,
            'upcoming_leaves': {
                'count': len(upcoming_leaves),
                'data': [{
                    'doctor_name': leave.doctor_id.name,
                    'start_date': leave.start_date,
                    'end_date': leave.end_date,
                    'reason': leave.reason,
                } for leave in upcoming_leaves]
            },
            'service_popularity': service_bookings
        }

    @api.model
    def quick_appointment_booking(self, patient_id, doctor_id, service_id, appointment_date, appointment_time):
        """Quick appointment booking for receptionist dashboard"""
        if not self.env.user.has_group('clinic_management.group_clinic_receptionist'):
            raise AccessError("Access Denied: Receptionist permissions required")
        
        appointment = self.env['clinic.appointment'].create({
            'patient_id': patient_id,
            'doctor_id': doctor_id,
            'service_id': service_id,
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
            'state': 'draft'
        })
        
        return {
            'success': True,
            'appointment_id': appointment.id,
            'message': 'Appointment created successfully'
        }

    @api.model
    def update_appointment_status(self, appointment_id, new_status):
        """Update appointment status from dashboard"""
        appointment = self.env['clinic.appointment'].browse(appointment_id)
        if not appointment.exists():
            return {'success': False, 'message': 'Appointment not found'}
        
        # Check permissions based on user role
        user = self.env.user
        if user.has_group('clinic_management.group_clinic_doctor'):
            # Doctors can only update their own appointments
            doctor = self.env['clinic.doctor'].search([('user_id', '=', user.id)], limit=1)
            if doctor and appointment.doctor_id.id != doctor.id:
                raise AccessError("Access Denied: You can only update your own appointments")
        elif not (user.has_group('clinic_management.group_clinic_receptionist') or 
                  user.has_group('clinic_management.group_clinic_admin')):
            raise AccessError("Access Denied: Insufficient permissions")
        
        appointment.state = new_status
        return {
            'success': True,
            'message': f'Appointment status updated to {new_status}'
        }
