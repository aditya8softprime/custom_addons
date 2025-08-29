from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ClinicPrescription(models.Model):
    _name = 'clinic.prescription'
    _description = 'Patient Prescription'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Reference', readonly=True, copy=False, default='New')
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True)
    appointment_id = fields.Many2one('clinic.appointment', string='Appointment')
    prescription_date = fields.Date(string='Date', default=fields.Date.context_today)
    notes = fields.Text(string='Notes')
    
    # Enhanced prescription input methods
    prescription_type = fields.Selection([
        ('digital', 'Digital Entry'),
        ('handwritten', 'Handwritten/Stylus'),
        ('scan', 'Scanned Document')
    ], string='Prescription Type', default='digital', required=True)

    prescription_image = fields.Binary(string='Handwritten/Scanned Prescription')
    prescription_image_filename = fields.Char(string='Prescription Image Filename')
    prescription_notes = fields.Text(string='Prescription Notes',
                                     help='Text notes for the prescription, including transcribed handwritten notes')

    medication_ids = fields.One2many('clinic.prescription.medication', 'prescription_id', 
                                    string='Medications')
    
    # Computed total for display
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_total_amount', 
                                  store=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('sent', 'Sent to Patient'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
  
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    
    @api.depends('medication_ids.subtotal')
    def _compute_total_amount(self):
        for prescription in self:
            prescription.total_amount = sum(prescription.medication_ids.mapped('subtotal'))
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('clinic.prescription') or 'New'
        return super(ClinicPrescription, self).create(vals_list)
    
    def action_confirm(self):
        self.write({'state': 'confirmed'})
        # Send email to patient if appointment is completed
        if self.appointment_id and self.appointment_id.state == 'completed':
            self.action_send_prescription_email()
    
    def action_cancel(self):
        self.write({'state': 'cancelled'})
    
    def action_send_prescription_email(self):
        """Send prescription to patient email"""
        if not self.patient_id.email:
            raise ValidationError(_('Patient email is not configured.'))
        
        template = self.env.ref('clinic_management.email_template_prescription', False)
        if template:
            template.send_mail(self.id, force_send=True)
            self.write({'state': 'sent'})
        
        return True


class ClinicPrescriptionMedication(models.Model):
    _name = 'clinic.prescription.medication'
    _description = 'Prescription Medication Line'
    
    prescription_id = fields.Many2one('clinic.prescription', string='Prescription', required=True)
    product_id = fields.Many2one('product.product', string='Medicine Product', 
                                domain=[('type', '=', 'consu')])
    medicine_name = fields.Char(string='Medicine Name', required=True)
    dosage = fields.Char(string='Dosage')
    frequency = fields.Char(string='Frequency')
    duration = fields.Char(string='Duration')
    quantity = fields.Float(string='Quantity', default=1.0)
    unit_price = fields.Monetary(string='Unit Price', currency_field='currency_id')
    subtotal = fields.Monetary(string='Subtotal', compute='_compute_subtotal', 
                              store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='prescription_id.currency_id', string='Currency')
    notes = fields.Text(string='Notes')
    
    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.medicine_name = self.product_id.name
            self.unit_price = self.product_id.list_price


class ClinicLabTest(models.Model):
    _name = 'clinic.lab.test'
    _description = 'Lab Test'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(string='Test Name', required=True)
    patient_id = fields.Many2one('clinic.patient', string='Patient', required=True)
    doctor_id = fields.Many2one('clinic.doctor', string='Doctor', required=True)
    appointment_id = fields.Many2one('clinic.appointment', string='Appointment')
    test_date = fields.Date(string='Date', default=fields.Date.context_today)
    notes = fields.Text(string='Notes')
    result = fields.Text(string='Result')
    result_document = fields.Binary(string='Result Document')
    result_document_filename = fields.Char(string='Result Document Filename')
    
    state = fields.Selection([
        ('requested', 'Requested'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='requested', tracking=True)
    
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
    
    def action_complete(self):
        self.write({'state': 'completed'})
    
    def action_cancel(self):
        self.write({'state': 'cancelled'})
