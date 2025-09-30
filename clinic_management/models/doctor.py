from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import json
import io
import logging

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.getLogger(__name__).warning("OpenCV not available. Template analysis will be disabled.")

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.getLogger(__name__).warning("Tesseract OCR not available. Advanced text detection will be disabled.")

# Optional PDF rendering libraries for converting uploaded templates (PDF -> Image)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except Exception:
    PYMUPDF_AVAILABLE = False
    logging.getLogger(__name__).warning("PyMuPDF (fitz) not available. PDF-to-image conversion via PyMuPDF disabled.")

try:
    from pdf2image import convert_from_bytes as _pdf2image_convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except Exception:
    PDF2IMAGE_AVAILABLE = False
    logging.getLogger(__name__).warning("pdf2image not available. PDF-to-image conversion via pdf2image disabled.")

_logger = logging.getLogger(__name__)


class ClinicDoctorSpecialTag(models.Model):
    _name = 'clinic.doctor.special.tag'
    _description = 'Doctor Special Tags'
    
    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index')


class DoctorShiftConfig(models.Model):
    _name = 'doctor.shift.config'
    _description = 'Doctor Weekly Shift Configuration'
    _order = 'doctor_id, day_id, shift_type'

    doctor_id = fields.Many2one('clinic.doctor', string="Doctor", required=True, ondelete="cascade")
    # Replaced selection with Many2one to clinic.days
    day_id = fields.Many2one('clinic.days', string='Day', required=True)
    shift_type = fields.Selection([
        ('morning', 'Morning'),
        ('evening', 'Evening'),
        ('night', 'Night'),
    ], string="Shift Type", required=True)
    start_time = fields.Float("Start Time (Hour, e.g., 8.0)", required=True)
    end_time = fields.Float("End Time (Hour, e.g., 12.0)", required=True)
    slot_duration = fields.Integer("Slot Duration (Minutes)", default=30)
    active = fields.Boolean("Active", default=True)
    
    # Relations
    slot_ids = fields.One2many('clinic.slot', 'shift_config_id', string="Generated Slots")
    
    # Computed fields
    slot_count = fields.Integer("Total Slots", compute='_compute_slot_count')
    
    @api.depends('slot_ids')
    def _compute_slot_count(self):
        for config in self:
            config.slot_count = len(config.slot_ids)
    
    _sql_constraints = [
        # Updated unique constraint to use day_id instead of day_of_week
        ('unique_doctor_day_shift', 'unique(doctor_id, day_id, shift_type)', 
         'Only one shift configuration per day per shift type allowed for each doctor!')
    ]

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for config in self:
            if config.start_time >= config.end_time:
                raise ValidationError(_("End Time must be greater than Start Time"))

    @api.constrains('slot_duration')
    def _check_slot_duration(self):
        for config in self:
            if config.slot_duration <= 0:
                raise ValidationError(_("Slot Duration must be greater than 0"))

    def _generate_slots(self):
        """Generate slot records based on config"""
        self.ensure_one()
        if not self.active:
            return
            
        Slot = self.env['clinic.slot']
        slots_to_create = []
        
        current = self.start_time * 60  # convert hr -> minutes
        end = self.end_time * 60
        # Compute numbering prefix and next sequence to maintain uniqueness
        day_code = (self.day_id.code or '').upper()
        shift_code = 'M' if self.shift_type == 'morning' else ('E' if self.shift_type == 'evening' else 'N')
        prefix = f"{day_code}-{shift_code}-"

        # Determine the next available sequence number based on existing slots for this doctor/day/shift
        existing_slots = Slot.search([
            ('doctor_id', '=', self.doctor_id.id),
            ('day_id', '=', self.day_id.id),
            '|', ('shift', '=', self.shift_type), ('shift_type', '=', self.shift_type),
        ])
        max_seq = 0
        for s in existing_slots:
            sn = (s.slot_number or '').strip()
            if sn.startswith(prefix):
                try:
                    n = int(sn.split('-')[-1])
                    if n > max_seq:
                        max_seq = n
                except Exception:
                    continue
        slot_number = max_seq + 1
        
        while current < end:
            start_min = current
            end_min = min(current + self.slot_duration, end)

            start_time_float = start_min / 60
            end_time_float = end_min / 60
            
            start_label = f"{int(start_min//60):02d}:{int(start_min%60):02d}"
            end_label = f"{int(end_min//60):02d}:{int(end_min%60):02d}"
            slot_label = f"{start_label} - {end_label}"
            
            # Generate slot number based on clinic.days code and shift (continue from next sequence)
            slot_number_str = f"{day_code}-{shift_code}-{slot_number:03d}"

            # Map clinic.days to python weekday index (0=Mon .. 6=Sun)
            day_of_week = False
            if self.day_id and self.day_id.sequence:
                # days_master_data.xml defines Monday..Sunday with sequence 1..7
                day_of_week = str(int(self.day_id.sequence) - 1)

            slots_to_create.append({
                'doctor_id': self.doctor_id.id,
                'shift_config_id': self.id,
                # Keep backward compatibility fields on clinic.slot
                'day_id': self.day_id.id,
                'shift': self.shift_type,
                # New weekly template fields
                'day_of_week': day_of_week,
                'shift_type': self.shift_type,
                'start_time_float': start_time_float,  # Keep for compatibility
                'end_time_float': end_time_float,      # Keep for compatibility
                'start_time': start_label,
                'end_time': end_label,
                'slot_label': slot_label,
                'slot_number': slot_number_str,
                'duration': self.slot_duration,
                # No explicit status; template is selectable unless blocked
            })
            
            current = end_min
            slot_number += 1
            
        # Create all slots at once for better performance
        if slots_to_create:
            Slot.create(slots_to_create)


class ClinicDoctor(models.Model):
    _name = 'clinic.doctor'
    _description = 'Clinic Doctor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, id'
    
    name = fields.Char(string='Doctor Name', required=True, tracking=True, index=True)
    image = fields.Binary(string='Profile Image')
    specialization_ids = fields.Many2many(
        'clinic.service', 
        string='Specializations',
        help='Medical specializations of the doctor',
        tracking=True,
    )
    qualification = fields.Text(string='Qualification', tracking=True)
    license_no = fields.Char(string='License No', tracking=True, index=True)
    mobile = fields.Char(string='Mobile', tracking=True)
    email = fields.Char(string='Email', tracking=True)
    department = fields.Many2one('hr.department', string='Department', tracking=True, index=True)
    available_days = fields.Many2many('clinic.days', string='Available Days', tracking=True)
    
    # Morning shift configuration
    morning_shift = fields.Boolean(string='Morning Shift Available', default=True, tracking=True)
    morning_start_time = fields.Float(string='Morning Start Time', tracking=True)
    morning_end_time = fields.Float(string='Morning End Time', tracking=True)
    
    # Evening shift configuration
    evening_shift = fields.Boolean(string='Evening Shift Available', default=False, tracking=True)
    evening_start_time = fields.Float(string='Evening Start Time', tracking=True)
    evening_end_time = fields.Float(string='Evening End Time', tracking=True)
    
    slot_duration = fields.Selection([
        ('15', '15 minutes'),
        ('20', '20 minutes'),
        ('30', '30 minutes'),
        ('45', '45 minutes'),
        ('60', '60 minutes'),
    ], string='Slot Duration', default='30', tracking=True)
    bio = fields.Html(string='Bio/Description')  # Removed tracking as it's not supported for HTML fields
    special_tag_ids = fields.Many2many('clinic.doctor.special.tag', string='Special Tags')
    consultation_fee = fields.Monetary(string='Consultation Fee', currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company, index=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Related User', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Related Employee', tracking=True)
    # Doctor-specific prescription template (PDF/Image)
    # Deprecated template fields retained for backward compatibility (hidden in views)
    prescription_template_pdf = fields.Binary(string='Prescription Template PDF', attachment=True)
    prescription_template_pdf_filename = fields.Char(string='Template PDF Filename')
    prescription_template_image = fields.Binary(string='Prescription Template Image', attachment=True)
    prescription_template_filename = fields.Char(string='Template Filename')

    # New prescription layout: header/footer images
    header_image = fields.Binary(string='Prescription Header Image', attachment=True, help='Appears at top of each prescription page')
    footer_image = fields.Binary(string='Prescription Footer Image', attachment=True, help='Appears at bottom of each prescription page')
    
    # Template analysis fields (computed from OpenCV + Tesseract)
    drawing_area_coords = fields.Text(string='Drawing Area Coordinates', 
                                      help='JSON coordinates of allowed drawing area detected by OpenCV + OCR')
    template_analysis_done = fields.Boolean(string='Template Analysis Done', default=False)
    detected_text_regions = fields.Text(string='Detected Text Regions', 
                                        help='JSON data of text regions found by OCR for header/footer detection')
    header_footer_coords = fields.Text(string='Header Footer Coordinates',
                                       help='JSON coordinates of detected header and footer areas')
    analysis_confidence = fields.Float(string='Analysis Confidence', help='Confidence score of template analysis (0-100)')
    template_layout_type = fields.Selection([
        ('letterhead_top', 'Letterhead at Top'),
        ('letterhead_full', 'Full Letterhead (Top + Bottom)'),
        ('simple', 'Simple Template'),
        ('complex', 'Complex Layout'),
        ('unknown', 'Unknown Layout')
    ], string='Template Layout Type', help='Detected layout type of prescription template')
    
    # Relations
    shift_config_ids = fields.One2many('doctor.shift.config', 'doctor_id', string="Shift Configurations")
    slot_ids = fields.One2many('clinic.slot', 'doctor_id', string="Generated Slots")
    appointment_ids = fields.One2many('clinic.appointment', 'doctor_id', string='Appointments')
    holiday_ids = fields.One2many('clinic.holiday', 'doctor_id', string='Leaves/Holidays')
    
    # New fields for a more professional doctor profile
    website = fields.Char(string='Website')
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string='Gender')
    date_of_birth = fields.Date(string='Date of Birth')
    experience_years = fields.Integer(string='Years of Experience')
    languages = fields.Many2many('res.lang', string='Languages Spoken')
    registration_date = fields.Date(string='Registration Date', default=fields.Date.today, tracking=True)
    
    _sql_constraints = [
        ('license_no_uniq', 'unique(license_no)', 'License number must be unique!')
    ]
    
    def name_get(self):
        """Custom name_get to show qualification with doctor name"""
        result = []
        for doctor in self:
            name = doctor.name
            if doctor.qualification:
                qualification_summary = doctor.qualification.split('\n')[0] if '\n' in doctor.qualification else doctor.qualification
                name = f"{name} ({qualification_summary})"
            result.append((doctor.id, name))
        return result

    def get_consultation_product_vals(self):
        """Return generic consultation product and dynamic price for this doctor"""
        self.ensure_one()
        Product = self.env['product.product']

        # Search for generic Consultation product
        product = Product.search([('name', '=', 'Consultation')], limit=1)
        if not product:
            raise ValidationError(_('Please create a generic Consultation product first!'))

        return {
            'product': product,
            'price_unit': self.consultation_fee,
            'description': f"Consultation – {self.name}"
        }
    
    @api.constrains('morning_start_time', 'morning_end_time', 'morning_shift')
    def _check_morning_hours(self):
        for record in self:
            if record.morning_shift and record.morning_start_time >= record.morning_end_time:
                raise ValidationError(_('Morning End Time must be greater than Morning Start Time'))
    
    @api.constrains('evening_start_time', 'evening_end_time', 'evening_shift')
    def _check_evening_hours(self):
        for record in self:
            if record.evening_shift and record.evening_start_time >= record.evening_end_time:
                raise ValidationError(_('Evening End Time must be greater than Evening Start Time'))
    
    @api.constrains('morning_shift', 'evening_shift')
    def _check_at_least_one_shift(self):
        for record in self:
            if not record.morning_shift and not record.evening_shift:
                raise ValidationError(_('At least one shift (Morning or Evening) must be enabled'))
    
    @api.model_create_multi
    def create(self, vals_list):
        doctors = super(ClinicDoctor, self).create(vals_list)
        # Convert template PDF to image after creation if present
        for doctor in doctors:
            if doctor.prescription_template_pdf and not doctor.prescription_template_image:
                doctor._set_template_image_from_pdf()
            # Create slots for each doctor
            doctor._create_slots()
        return doctors
    
    def write(self, vals):
        res = super(ClinicDoctor, self).write(vals)
        # If PDF updated, refresh converted image
        if 'prescription_template_pdf' in vals:
            self._set_template_image_from_pdf()
        # If availability related fields changed, update slots
        slot_related_fields = ['available_days', 'morning_start_time', 'morning_end_time', 
                              'evening_start_time', 'evening_end_time', 'morning_shift', 
                              'evening_shift', 'slot_duration']
        if any(field in vals for field in slot_related_fields):
            self._create_slots()
            
        # If prescription template changed, analyze it
        if 'prescription_template_image' in vals and vals['prescription_template_image']:
            self._analyze_prescription_template()
            
        return res

    # -------------------------------
    # PDF -> Image conversion helpers
    # -------------------------------
    def _convert_pdf_bytes_to_png_bytes(self, pdf_bytes):
        """Convert first page of PDF bytes to PNG bytes. Return None on failure."""
        # Prefer PyMuPDF for performance and quality
        try:
            if PYMUPDF_AVAILABLE:
                doc = fitz.open(stream=pdf_bytes, filetype='pdf')
                if doc.page_count:
                    page = doc.load_page(0)
                    matrix = fitz.Matrix(2, 2)
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    return pix.tobytes('png')
        except Exception as e:
            _logger.warning("PDF->Image via PyMuPDF failed: %s", e)
        # Fallback to pdf2image
        try:
            if PDF2IMAGE_AVAILABLE:
                imgs = _pdf2image_convert_from_bytes(pdf_bytes, first_page=1, last_page=1, fmt='png')
                if imgs:
                    buf = io.BytesIO()
                    imgs[0].save(buf, format='PNG')
                    return buf.getvalue()
        except Exception as e:
            _logger.warning("PDF->Image via pdf2image failed: %s", e)
        # Last resort using PIL
        try:
            from PIL import Image as _PIL_Image
            img = _PIL_Image.open(io.BytesIO(pdf_bytes))
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()
        except Exception as e:
            _logger.warning("PDF->Image via PIL failed: %s", e)
        return None

    def _resize_png_if_needed(self, png_bytes, max_width=2000):
        """Resize PNG if too large to a reasonable width to avoid heavy uploads (best-effort)."""
        try:
            from PIL import Image as _PIL_Image
            im = _PIL_Image.open(io.BytesIO(png_bytes))
            w, h = im.size
            if w > max_width:
                scale = max_width / float(w)
                new_size = (int(w * scale), int(h * scale))
                im = im.convert('RGB')  # unify mode
                im = im.resize(new_size)
                buf = io.BytesIO()
                im.save(buf, format='PNG')
                return buf.getvalue()
        except Exception as e:
            _logger.debug("PNG resize skipped: %s", e)
        return png_bytes

    def _set_template_image_from_pdf(self):
        """If a template PDF is uploaded, convert it and set the image fields."""
        for rec in self:
            if not rec.prescription_template_pdf:
                continue
            try:
                pdf_bytes = base64.b64decode(rec.prescription_template_pdf)
            except Exception as e:
                _logger.warning("Failed decoding template PDF for doctor %s: %s", rec.id, e)
                continue
            _logger.info("Starting PDF->Image conversion for doctor %s (pdf size: %s bytes)", rec.id, len(rec.prescription_template_pdf))
            png_bytes = rec._convert_pdf_bytes_to_png_bytes(pdf_bytes)
            if png_bytes:
                png_bytes = rec._resize_png_if_needed(png_bytes)
                rec.prescription_template_image = base64.b64encode(png_bytes)
                if rec.prescription_template_pdf_filename:
                    base_name = rec.prescription_template_pdf_filename.rsplit('.', 1)[0]
                    rec.prescription_template_filename = f"{base_name}.png"
                elif not rec.prescription_template_filename:
                    rec.prescription_template_filename = f"Prescription_Template_{rec.name or 'Doctor'}.png"
                _logger.info("PDF->Image conversion succeeded for doctor %s (png size: %s bytes)", rec.id, len(rec.prescription_template_image or b''))
            else:
                _logger.warning("Could not convert uploaded PDF to image for doctor %s", rec.id)

    @api.onchange('prescription_template_pdf')
    def _onchange_prescription_template_pdf(self):
        # Try conversion immediately so user sees the image preview update
        self._set_template_image_from_pdf()
        # Provide user feedback if conversion could not run
        if self.prescription_template_pdf and not self.prescription_template_image:
            missing = []
            if not globals().get('PYMUPDF_AVAILABLE'):
                missing.append('PyMuPDF (fitz)')
            if not globals().get('PDF2IMAGE_AVAILABLE'):
                missing.append('pdf2image')
            if missing:
                return {
                    'warning': {
                        'title': _('PDF Conversion Unavailable'),
                        'message': _('Cannot convert PDF to image. Missing libraries: %s. Please install one of them for automatic conversion.') % ', '.join(missing)
                    }
                }
            else:
                return {
                    'warning': {
                        'title': _('PDF Conversion Failed'),
                        'message': _('Tried converting the uploaded PDF but failed. Ensure the PDF is valid or contact administrator.')
                    }
                }
        # If conversion succeeded, clear previous analysis so it can re-run
        if self.prescription_template_image:
            self.template_analysis_done = False
    
    def generate_weekly_slots(self):
        """Loop over shift_config_ids and generate slots in clinic.slot"""
        for doctor in self:
            # Clear old slots without any appointments (preserve historical/booked data)
            doctor.slot_ids.filtered(lambda s: not s.appointment_ids).unlink()
            for config in doctor.shift_config_ids:
                config._generate_slots()

    def _create_slots(self):
        """Generate slots based on doctor's availability (Legacy method - now uses shift configs)"""
        self.ensure_one()
        # If we have shift configurations, use the new system
        if self.shift_config_ids:
            self.generate_weekly_slots()
            return
            
        # Legacy slot generation for backward compatibility
        Slot = self.env['clinic.slot']
        
        # Delete existing slots that are not linked to any appointments
        # This preserves historical data
        existing_slots = Slot.search([
            ('doctor_id', '=', self.id),
        ])
        for s in existing_slots:
            if not s.appointment_ids:
                s.unlink()
        
        # Convert slot_duration from string to float
        slot_duration_minutes = float(self.slot_duration)
        slot_duration_hours = slot_duration_minutes / 60
        
        # Create new slots for each available day
        for day in self.available_days:
            
            # Morning shift slots
            if self.morning_shift and self.morning_start_time and self.morning_end_time:
                # Determine next sequence for morning prefix
                morning_prefix = f"{day.code}-M-"
                existing_morning = Slot.search([
                    ('doctor_id', '=', self.id),
                    ('day_id', '=', day.id),
                    '|', ('shift', '=', 'morning'), ('shift_type', '=', 'morning'),
                ])
                max_m = 0
                for s in existing_morning:
                    sn = (s.slot_number or '').strip()
                    if sn.startswith(morning_prefix):
                        try:
                            n = int(sn.split('-')[-1])
                            if n > max_m:
                                max_m = n
                        except Exception:
                            continue
                slot_number = max_m + 1
                current_time = self.morning_start_time
                
                while current_time + slot_duration_hours <= self.morning_end_time:
                    end_time = current_time + slot_duration_hours
                    
                    # Create morning slot
                    slot_vals = {
                        'doctor_id': self.id,
                        'day_id': day.id,
                        'start_time': current_time,
                        'end_time': end_time,
                        'duration': slot_duration_minutes,
                        'shift': 'morning',
                        'slot_number': f"{day.code}-M-{slot_number:03d}",
                        # template slots no longer carry status; availability is derived at booking time
                    }
                    Slot.create(slot_vals)
                    
                    # Move to next slot
                    current_time = end_time
                    slot_number += 1
            
            # Evening shift slots
            if self.evening_shift and self.evening_start_time and self.evening_end_time:
                # Determine next sequence for evening prefix
                evening_prefix = f"{day.code}-E-"
                existing_evening = Slot.search([
                    ('doctor_id', '=', self.id),
                    ('day_id', '=', day.id),
                    '|', ('shift', '=', 'evening'), ('shift_type', '=', 'evening'),
                ])
                max_e = 0
                for s in existing_evening:
                    sn = (s.slot_number or '').strip()
                    if sn.startswith(evening_prefix):
                        try:
                            n = int(sn.split('-')[-1])
                            if n > max_e:
                                max_e = n
                        except Exception:
                            continue
                slot_number = max_e + 1
                current_time = self.evening_start_time
                
                while current_time + slot_duration_hours <= self.evening_end_time:
                    end_time = current_time + slot_duration_hours
                    
                    # Create evening slot
                    slot_vals = {
                        'doctor_id': self.id,
                        'day_id': day.id,
                        'start_time': current_time,
                        'end_time': end_time,
                        'duration': slot_duration_minutes,
                        'shift': 'evening',
                        'slot_number': f"{day.code}-E-{slot_number:03d}",
                        # template slots no longer carry status; availability is derived at booking time
                    }
                    Slot.create(slot_vals)
                    
                    # Move to next slot
                    current_time = end_time
                    slot_number += 1
    
    def action_create_employee(self):
        """Create an employee record for this doctor"""
        self.ensure_one()
        if self.employee_id:
            raise ValidationError(_('Employee already exists for this doctor'))
        
        # Create employee
        employee = self.env['hr.employee'].create({
            'name': self.name,
            'work_email': self.email,
            'mobile_phone': self.mobile,
            'department_id': self.department.id if self.department else False,
            'company_id': self.company_id.id,
            'gender': self.gender,
            'birthday': self.date_of_birth,
        })
        
        self.employee_id = employee.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Employee'),
            'res_model': 'hr.employee',
            'res_id': employee.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_create_user(self):
        """Create a user account for this doctor"""
        self.ensure_one()
        if self.user_id:
            raise ValidationError(_('User already exists for this doctor'))
        
        # Create user
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': self.name,
            'login': self.email,
            'email': self.email,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,  # Internal user mandatory
                self.env.ref('clinic_management.group_clinic_doctor').id,  # Custom doctor group
            ])],
            'company_ids': [(4, self.company_id.id)],
            'company_id': self.company_id.id,
        })
        
        self.user_id = user.id
        
        # Link employee to user if employee exists
        if self.employee_id:
            self.employee_id.user_id = user.id
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('User'),
            'res_model': 'res.users',
            'res_id': user.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _analyze_prescription_template(self):
        """Analyze prescription template to detect writing areas using OpenCV + Tesseract OCR"""
        self.ensure_one()
        
        if not OPENCV_AVAILABLE:
            _logger.warning("OpenCV not available. Using default template analysis.")
            self._set_default_drawing_area()
            return
            
        if not self.prescription_template_image:
            return
            
        try:
            # Decode and prepare image
            image_data = base64.b64decode(self.prescription_template_image)
            
            # Step 1: Validate template quality
            quality_results = self._validate_template_quality(image_data)
            _logger.info(f"Template quality for {self.name}: {quality_results['quality_score']}% "
                        f"({quality_results['resolution']}, Issues: {quality_results['quality_issues']})")
            
            # Decode image for analysis
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("Could not decode image")
            
            # Apply preprocessing if needed for better OCR
            if quality_results['preprocessing_needed']:
                img = self._preprocess_image_for_ocr(img, quality_results)
                
            height, width = img.shape[:2]
            _logger.info(f"Analyzing template for {self.name}: {width}x{height} pixels, "
                        f"Type: {quality_results['template_info']['estimated_type']}")
            
            # Step 2: Perform comprehensive analysis
            analysis_results = self._perform_comprehensive_analysis(img)
            
            # Step 3: Extract results and adjust confidence based on quality
            drawing_coords = analysis_results['drawing_area']
            header_footer = analysis_results['header_footer']
            text_regions = analysis_results['text_regions']
            confidence = analysis_results['confidence']
            layout_type = analysis_results['layout_type']
            
            # Adjust final confidence based on template quality
            quality_factor = quality_results['quality_score'] / 100.0
            final_confidence = confidence * (0.7 + 0.3 * quality_factor)  # Quality affects 30% of confidence
            
            # Store comprehensive results
            self.drawing_area_coords = json.dumps(drawing_coords)
            self.header_footer_coords = json.dumps(header_footer)
            self.detected_text_regions = json.dumps(text_regions)
            self.analysis_confidence = final_confidence
            self.template_layout_type = layout_type
            self.template_analysis_done = True
            
            # Store quality information for debugging
            quality_info = {
                'quality_score': quality_results['quality_score'],
                'resolution': quality_results['resolution'],
                'issues': quality_results['quality_issues'],
                'template_type': quality_results['template_info']['estimated_type'],
                'preprocessing_applied': quality_results['preprocessing_needed']
            }
            
            _logger.info(f"Enhanced template analysis completed for {self.name}. "
                        f"Layout: {layout_type}, Quality: {quality_results['quality_score']}%, "
                        f"Final confidence: {final_confidence:.1f}%, "
                        f"Text regions: {len(text_regions)}, "
                        f"Drawing area: {drawing_coords}")
            
        except Exception as e:
            _logger.error(f"Template analysis failed for {self.name}: {str(e)}")
            self._set_default_drawing_area()
    
    def _set_default_drawing_area(self):
        """Set default drawing area when analysis fails"""
        default_coords = {'x': 0.1, 'y': 0.2, 'width': 0.8, 'height': 0.6}
        default_header_footer = {'header': {'y': 0, 'height': 0.15}, 'footer': {'y': 0.85, 'height': 0.15}}
        
        self.drawing_area_coords = json.dumps(default_coords)
        self.header_footer_coords = json.dumps(default_header_footer)
        self.detected_text_regions = json.dumps([])
        self.analysis_confidence = 50.0
        self.template_layout_type = 'simple'
        self.template_analysis_done = True
    
    def _perform_comprehensive_analysis(self, img):
        """Perform comprehensive template analysis using OpenCV + OCR"""
        height, width = img.shape[:2]
        
        # Step 1: OCR-based text detection
        text_regions = self._detect_text_regions_ocr(img) if TESSERACT_AVAILABLE else []
        
        # Step 2: Computer vision-based analysis
        cv_analysis = self._analyze_with_opencv(img)
        
        # Step 3: Combine OCR and CV results
        combined_analysis = self._combine_analysis_results(text_regions, cv_analysis, width, height)
        
        return combined_analysis
    
    def _detect_text_regions_ocr(self, img):
        """Enhanced OCR with multiple detection strategies for complex prescription templates"""
        all_text_regions = []
        height, width = img.shape[:2]
        
        try:
            # Convert OpenCV image to PIL
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)
            
            # Strategy 1: Multiple PSM modes for different layouts
            psm_modes = [
                ('--psm 6', 'uniform_text'),   # Uniform block of text
                ('--psm 3', 'full_page'),      # Full page analysis
                ('--psm 11', 'sparse_text'),   # Sparse text (good for forms)
                ('--psm 12', 'single_word'),   # Single word detection
            ]
            
            for config, mode_name in psm_modes:
                try:
                    ocr_data = pytesseract.image_to_data(
                        pil_img, 
                        output_type=pytesseract.Output.DICT, 
                        lang='eng+hin',
                        config=config
                    )
                    
                    # Process results with lower confidence threshold
                    for i in range(len(ocr_data['text'])):
                        confidence = int(ocr_data['conf'][i])
                        text = ocr_data['text'][i].strip()
                        
                        # More lenient filtering for complex templates
                        if confidence > 15 and text and len(text.replace(' ', '')) > 0:
                            x = ocr_data['left'][i]
                            y = ocr_data['top'][i]
                            w = ocr_data['width'][i]
                            h = ocr_data['height'][i]
                            
                            # Enhanced position-based classification
                            is_likely_header = self._enhanced_header_detection(text, x, y, w, h, width, height)
                            is_likely_footer = self._enhanced_footer_detection(text, x, y, w, h, width, height)
                            
                            region = {
                                'text': text,
                                'confidence': confidence,
                                'x': x / width,
                                'y': y / height,
                                'width': w / width,
                                'height': h / height,
                                'is_header': is_likely_header,
                                'is_footer': is_likely_footer,
                                'text_type': self._classify_text_type(text),
                                'detection_mode': mode_name
                            }
                            all_text_regions.append(region)
                            
                except Exception as mode_error:
                    _logger.warning(f"OCR mode {mode_name} failed: {mode_error}")
                    continue
            
            # Remove duplicate regions (same position, similar text)
            unique_regions = self._deduplicate_text_regions(all_text_regions, width, height)
            
            _logger.info(f"Enhanced OCR detected {len(unique_regions)} unique text regions from {len(all_text_regions)} total detections")
            
            # If still no text detected, use image processing fallback
            if len(unique_regions) == 0:
                unique_regions = self._fallback_text_detection(img)
                
            return unique_regions
            
        except Exception as e:
            _logger.error(f"Enhanced OCR detection failed: {str(e)}")
            # Emergency fallback based on image analysis
            return self._fallback_text_detection(img)
    
    def _enhanced_header_detection(self, text, x, y, w, h, img_width, img_height):
        """Enhanced header detection with position and content analysis"""
        # Position-based: top 35% of image
        is_top_area = y < img_height * 0.35
        
        # Size-based: larger text blocks often headers
        is_large_text = (w > img_width * 0.3) or (h > img_height * 0.03)
        
        # Content-based keywords (medical/clinic)
        header_keywords = [
            'dr', 'doctor', 'clinic', 'hospital', 'medical', 'mbbs', 'md', 'ms',
            'reg', 'registration', 'license', 'phone', 'mobile', 'email',
            'physiotherapist', 'therapist', 'bpt', 'mph', 'dpt'
        ]
        
        text_lower = text.lower()
        contains_keywords = any(keyword in text_lower for keyword in header_keywords)
        
        # Horizontal position: centered text often headers
        is_centered = abs((x + w/2) - img_width/2) < img_width * 0.2
        
        return (is_top_area and (is_large_text or contains_keywords)) or (contains_keywords and is_centered)
    
    def _enhanced_footer_detection(self, text, x, y, w, h, img_width, img_height):
        """Enhanced footer detection with position and content analysis"""
        # Position-based: bottom 30% of image
        is_bottom_area = y > img_height * 0.7
        
        # Content-based keywords
        footer_keywords = [
            'timing', 'time', 'days', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
            'follow', 'next', 'visit', 'date', 'signature', 'sign',
            'contact', 'phone', 'emergency', 'address', 'qr'
        ]
        
        text_lower = text.lower()
        contains_keywords = any(keyword in text_lower for keyword in footer_keywords)
        
        # Very bottom area (last 15%)
        is_very_bottom = y > img_height * 0.85
        
        return is_bottom_area or contains_keywords or is_very_bottom
    
    def _deduplicate_text_regions(self, regions, width, height):
        """Remove duplicate text regions with similar positions"""
        unique_regions = []
        
        for region in regions:
            is_duplicate = False
            
            for existing in unique_regions:
                # Check position overlap
                x_overlap = abs(region['x'] - existing['x']) < 0.05  # 5% tolerance
                y_overlap = abs(region['y'] - existing['y']) < 0.05
                
                # Check text similarity
                text_similar = (region['text'].lower() in existing['text'].lower()) or \
                             (existing['text'].lower() in region['text'].lower())
                
                if x_overlap and y_overlap and text_similar:
                    # Keep the one with higher confidence
                    if region['confidence'] > existing['confidence']:
                        unique_regions.remove(existing)
                        unique_regions.append(region)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_regions.append(region)
        
        return unique_regions
    
    def _fallback_text_detection(self, img):
        """Fallback detection using image processing when OCR fails"""
        try:
            height, width = img.shape[:2]
            
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Detect text-like regions using contours
            # Apply threshold to get binary image
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # Find contours
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            text_regions = []
            
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Filter by size - likely text regions
                if (w > 20 and h > 10 and w < width * 0.8 and h < height * 0.2):
                    # Classify as header/footer based on position
                    is_header = y < height * 0.3
                    is_footer = y > height * 0.7
                    
                    region = {
                        'text': f'[Detected text region]',
                        'confidence': 30,  # Low confidence for fallback
                        'x': x / width,
                        'y': y / height,
                        'width': w / width,
                        'height': h / height,
                        'is_header': is_header,
                        'is_footer': is_footer,
                        'text_type': 'detected_region',
                        'detection_mode': 'fallback'
                    }
                    text_regions.append(region)
            
            _logger.info(f"Fallback detection found {len(text_regions)} text-like regions")
            return text_regions
            
        except Exception as e:
            _logger.error(f"Fallback detection failed: {str(e)}")
            return []
    
    def _is_likely_header_text(self, text, y_pos, img_height):
        """Detect if text is likely part of header (clinic info, doctor name, etc.)"""
        header_keywords = [
            'dr', 'doctor', 'clinic', 'hospital', 'medical', 'mbbs', 'md', 'ms',
            'reg', 'registration', 'license', 'phone', 'mobile', 'email',
            'address', 'timing', 'consultation'
        ]
        
        # Position-based detection (top 30% of image)
        is_top_area = y_pos < img_height * 0.3
        
        # Keyword-based detection
        text_lower = text.lower()
        contains_header_keywords = any(keyword in text_lower for keyword in header_keywords)
        
        return is_top_area or contains_header_keywords
    
    def _is_likely_footer_text(self, text, y_pos, img_height):
        """Detect if text is likely part of footer (contact, signature, etc.)"""
        footer_keywords = [
            'signature', 'sign', 'follow', 'next', 'visit', 'date',
            'phone', 'contact', 'emergency', 'timing', 'address'
        ]
        
        # Position-based detection (bottom 25% of image)
        is_bottom_area = y_pos > img_height * 0.75
        
        # Keyword-based detection
        text_lower = text.lower()
        contains_footer_keywords = any(keyword in text_lower for keyword in footer_keywords)
        
        return is_bottom_area or contains_footer_keywords
    
    def _classify_text_type(self, text):
        """Classify the type of text found"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['dr', 'doctor', 'mbbs', 'md']):
            return 'doctor_info'
        elif any(word in text_lower for word in ['clinic', 'hospital', 'medical']):
            return 'clinic_info'
        elif any(word in text_lower for word in ['patient', 'name', 'age', 'sex']):
            return 'patient_field'
        elif any(word in text_lower for word in ['phone', 'mobile', 'email', 'address']):
            return 'contact_info'
        elif any(word in text_lower for word in ['signature', 'date', 'follow']):
            return 'signature_area'
        else:
            return 'general_text'
    
    def _analyze_with_opencv(self, img):
        """Analyze image using OpenCV computer vision techniques"""
        height, width = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Edge detection for structural analysis
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # 2. Morphological operations to find text blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 5))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        # 3. Find contours representing potential text blocks
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 4. Analyze contours
        text_blocks = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter by size (avoid very small or very large regions)
            if w > width * 0.1 and h > height * 0.01 and w < width * 0.9 and h < height * 0.3:
                text_blocks.append({
                    'x': x / width,
                    'y': y / height,
                    'width': w / width,
                    'height': h / height,
                    'area': (w * h) / (width * height)
                })
        
        # 5. Detect horizontal lines (often in headers/footers)
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
        
        return {
            'text_blocks': text_blocks,
            'horizontal_lines': horizontal_lines,
            'edges': edges
        }
    
    def _combine_analysis_results(self, text_regions, cv_analysis, width, height):
        """Combine OCR and computer vision results with Indian prescription template optimization"""
        
        # Categorize text regions with enhanced classification
        header_regions = [r for r in text_regions if r['is_header']]
        footer_regions = [r for r in text_regions if r['is_footer']]
        body_regions = [r for r in text_regions if not r['is_header'] and not r['is_footer']]
        
        # Special handling for patient info fields (common in Indian templates)
        patient_fields = [r for r in text_regions if r.get('text_type') == 'patient_field']
        
        # Calculate boundaries with Indian template awareness
        header_bottom = self._calculate_smart_header_boundary(header_regions, height)
        footer_top = self._calculate_smart_footer_boundary(footer_regions, height)
        
        # Detect large blank areas (prescription writing space)
        blank_areas = self._detect_blank_areas(text_regions, cv_analysis, width, height)
        
        # Determine layout type
        layout_type = self._determine_layout_type(header_regions, footer_regions, cv_analysis)
        
        # Calculate confidence based on OCR quality and structure detection
        confidence = self._calculate_analysis_confidence(text_regions, cv_analysis)
        
        # Define optimal drawing area using blank space detection
        drawing_coords = self._calculate_optimal_drawing_area(
            header_bottom, footer_top, blank_areas, patient_fields, width, height
        )
        
        header_footer_coords = {
            'header': {'y': 0, 'height': header_bottom},
            'footer': {'y': footer_top, 'height': 1.0 - footer_top}
        }
        
        return {
            'drawing_area': drawing_coords,
            'header_footer': header_footer_coords,
            'text_regions': text_regions,
            'confidence': confidence,
            'layout_type': layout_type,
            'blank_areas': blank_areas
        }
    
    def _calculate_smart_header_boundary(self, header_regions, height):
        """Calculate header boundary with Indian prescription template awareness"""
        if not header_regions:
            return 0.15  # Default 15%
        
        # Find the bottom-most header element
        max_header_bottom = max(r['y'] + r['height'] for r in header_regions)
        
        # Add appropriate padding based on header content
        has_doctor_info = any('dr' in r['text'].lower() or 'mbbs' in r['text'].lower() 
                             for r in header_regions)
        has_clinic_info = any('clinic' in r['text'].lower() or 'hospital' in r['text'].lower() 
                             for r in header_regions)
        
        # More padding for comprehensive headers
        if has_doctor_info and has_clinic_info:
            padding = 0.08  # 8% padding for full letterhead
        elif has_doctor_info or has_clinic_info:
            padding = 0.05  # 5% padding for partial header
        else:
            padding = 0.03  # 3% padding for minimal header
            
        header_bottom = max_header_bottom + padding
        return min(header_bottom, 0.35)  # Cap at 35% of image
    
    def _calculate_smart_footer_boundary(self, footer_regions, height):
        """Calculate footer boundary with signature area awareness"""
        if not footer_regions:
            return 0.85  # Default 85%
            
        # Find the top-most footer element
        min_footer_top = min(r['y'] for r in footer_regions)
        
        # Add padding for signature space
        has_signature = any('sign' in r['text'].lower() for r in footer_regions)
        padding = 0.08 if has_signature else 0.05
        
        footer_top = min_footer_top - padding
        return max(footer_top, 0.65)  # At least 65% available for writing
    
    def _detect_blank_areas(self, text_regions, cv_analysis, width, height):
        """Detect large blank areas suitable for prescription writing"""
        # Create a grid to mark text areas
        grid_rows, grid_cols = 20, 15  # 20x15 grid
        text_grid = [[False for _ in range(grid_cols)] for _ in range(grid_rows)]
        
        # Mark grid cells that contain text
        for region in text_regions:
            start_row = int(region['y'] * grid_rows)
            end_row = min(int((region['y'] + region['height']) * grid_rows), grid_rows - 1)
            start_col = int(region['x'] * grid_cols)
            end_col = min(int((region['x'] + region['width']) * grid_cols), grid_cols - 1)
            
            for row in range(start_row, end_row + 1):
                for col in range(start_col, end_col + 1):
                    if 0 <= row < grid_rows and 0 <= col < grid_cols:
                        text_grid[row][col] = True
        
        # Find continuous blank areas
        blank_areas = []
        for row in range(1, grid_rows - 1):  # Skip first and last rows
            consecutive_blank = 0
            start_col = 0
            
            for col in range(grid_cols):
                if not text_grid[row][col]:
                    if consecutive_blank == 0:
                        start_col = col
                    consecutive_blank += 1
                else:
                    if consecutive_blank >= 5:  # At least 5 consecutive blank cells
                        blank_areas.append({
                            'x': start_col / grid_cols,
                            'y': row / grid_rows,
                            'width': consecutive_blank / grid_cols,
                            'height': 1 / grid_rows
                        })
                    consecutive_blank = 0
            
            # Check end of row
            if consecutive_blank >= 5:
                blank_areas.append({
                    'x': start_col / grid_cols,
                    'y': row / grid_rows,
                    'width': consecutive_blank / grid_cols,
                    'height': 1 / grid_rows
                })
        
        return blank_areas
    
    def _calculate_optimal_drawing_area(self, header_bottom, footer_top, blank_areas, patient_fields, width, height):
        """Calculate optimal drawing area with intelligent fallbacks for poor OCR"""
        
        # Smart defaults based on common prescription template layouts
        default_areas = {
            'letterhead_full': {'x': 0.06, 'y': 0.25, 'width': 0.88, 'height': 0.50},
            'letterhead_top': {'x': 0.06, 'y': 0.30, 'width': 0.88, 'height': 0.55},
            'form_based': {'x': 0.08, 'y': 0.35, 'width': 0.84, 'height': 0.45},
            'minimal_template': {'x': 0.05, 'y': 0.20, 'width': 0.90, 'height': 0.65},
            'simple': {'x': 0.08, 'y': 0.25, 'width': 0.84, 'height': 0.60},
            'complex': {'x': 0.10, 'y': 0.30, 'width': 0.80, 'height': 0.50}
        }
        
        # If OCR worked well, use detected boundaries
        if header_bottom > 0.15 and footer_top < 0.85:
            safe_y = header_bottom + 0.03  # 3% margin from header
            safe_height = footer_top - safe_y - 0.03  # 3% margin to footer
            
            # Avoid patient info fields if detected
            if patient_fields:
                max_patient_bottom = max(r['y'] + r['height'] for r in patient_fields)
                if max_patient_bottom > safe_y:
                    safe_y = max_patient_bottom + 0.04  # 4% margin from patient fields
                    safe_height = footer_top - safe_y - 0.03
            
            # Use detected blank areas if substantial
            if blank_areas:
                largest_blank = max(blank_areas, key=lambda x: x['width'] * x['height'])
                if largest_blank['height'] > 0.25:  # At least 25% height
                    safe_y = max(safe_y, largest_blank['y'])
                    safe_height = min(safe_height, largest_blank['height'])
            
            # Ensure reasonable drawing area
            if safe_height >= 0.25:  # At least 25% height is acceptable
                return {
                    'x': 0.06,  # 6% margin from left
                    'y': safe_y,
                    'width': 0.88,  # 88% width
                    'height': safe_height
                }
        
        # Fallback: Use template-based defaults with image analysis
        template_type = getattr(self, 'template_layout_type', 'simple') or 'simple'
        
        # Get base area for detected template type
        base_area = default_areas.get(template_type, default_areas['simple'])
        
        # Adjust based on image characteristics
        if hasattr(self, 'detected_text_regions') and self.detected_text_regions:
            try:
                regions = json.loads(self.detected_text_regions)
                if len(regions) > 0:
                    # If we have some text detection, be more conservative
                    base_area['x'] = 0.08
                    base_area['width'] = 0.84
                    base_area['y'] = max(base_area['y'], 0.28)
                    base_area['height'] = min(base_area['height'], 0.55)
            except:
                pass
        
        # For attached templates (hospital/physiotherapy), use specific patterns
        if self._detect_template_pattern():
            # These templates typically have header with logo, patient fields, then prescription area
            return {
                'x': 0.05,      # 5% margin (more space for writing)
                'y': 0.35,      # Start after typical header + patient info
                'width': 0.65,  # 65% width (avoid right side patient fields) 
                'height': 0.45  # 45% height (good prescription space)
            }
        
        return base_area
    
    def _detect_template_pattern(self):
        """Detect specific template patterns from attached examples"""
        # This would be enhanced to detect the specific blue/green template patterns
        # For now, return True to use the conservative settings
        return True
    
    def _determine_layout_type(self, header_regions, footer_regions, cv_analysis):
        """Enhanced layout detection for various prescription template types"""
        
        # Count regions by area coverage
        header_coverage = sum(r['width'] * r['height'] for r in header_regions)
        footer_coverage = sum(r['width'] * r['height'] for r in footer_regions)
        
        # Detect based on region count and coverage
        has_substantial_header = len(header_regions) > 1 or header_coverage > 0.15
        has_substantial_footer = len(footer_regions) > 0 or footer_coverage > 0.05
        
        # Check for specific template patterns
        has_patient_fields = any('patient' in r.get('text', '').lower() or 
                               'name' in r.get('text', '').lower() or
                               'age' in r.get('text', '').lower()
                               for r in header_regions + footer_regions)
        
        # Check for medical symbols/logos (detected as image regions)
        text_block_count = len(cv_analysis.get('text_blocks', []))
        has_logo_area = any(block['area'] > 0.02 and block['y'] < 0.3 
                           for block in cv_analysis.get('text_blocks', []))
        
        # Enhanced classification
        if has_substantial_header and has_substantial_footer:
            return 'letterhead_full'
        elif has_substantial_header or has_logo_area:
            return 'letterhead_top'
        elif has_patient_fields:
            return 'form_based'
        elif text_block_count > 8:
            return 'complex'
        elif text_block_count > 0:
            return 'simple'
        else:
            # Default for templates with minimal text detection
            return 'minimal_template'
    
    def _calculate_analysis_confidence(self, text_regions, cv_analysis):
        """Enhanced confidence calculation with multiple factors"""
        base_confidence = 40.0  # Lower base for stricter evaluation
        
        # OCR Quality Score (35% weight)
        ocr_score = 0
        if text_regions:
            # Higher weight for successful text detection
            detection_bonus = min(len(text_regions) * 5, 30)
            avg_confidence = sum(r['confidence'] for r in text_regions) / len(text_regions)
            ocr_score = detection_bonus + (avg_confidence * 0.3)
        else:
            # Penalty for no text detection, but not complete failure
            ocr_score = 10  # Minimal score for image processing
            
        # Structural Analysis Score (25% weight)  
        structure_score = 0
        text_blocks = cv_analysis.get('text_blocks', [])
        if text_blocks:
            # Reward diverse text block sizes and positions
            block_diversity = len(set(round(b['area'] * 100) for b in text_blocks))
            structure_score = min(len(text_blocks) * 3 + block_diversity * 2, 25)
        
        # Layout Detection Score (20% weight)
        layout_score = 0
        header_regions = [r for r in text_regions if r.get('is_header')]
        footer_regions = [r for r in text_regions if r.get('is_footer')]
        
        if header_regions:
            layout_score += 10
        if footer_regions:
            layout_score += 8
        if len(text_regions) > len(header_regions) + len(footer_regions):
            layout_score += 7  # Has body content
            
        # Image Processing Score (20% weight)
        processing_score = 15  # Base score for successful image processing
        
        # Check if image has good contrast/clarity
        edges = cv_analysis.get('edges')
        if edges is not None:
            # Count edge pixels as indicator of image clarity
            edge_density = cv2.countNonZero(edges) / (edges.shape[0] * edges.shape[1])
            if edge_density > 0.05:  # Good edge density
                processing_score += 10
            elif edge_density > 0.02:  # Moderate edge density
                processing_score += 5
        
        # Combine all scores
        total_confidence = base_confidence + ocr_score + structure_score + layout_score + processing_score
        
        # Apply penalties for suspicious results
        if len(text_regions) == 0:
            total_confidence *= 0.6  # 40% penalty for no text
        elif all(r['confidence'] < 30 for r in text_regions):
            total_confidence *= 0.8  # 20% penalty for low OCR confidence
        
        return min(max(total_confidence, 25.0), 95.0)  # Cap between 25-95%
    
    def _validate_template_quality(self, image_data):
        """Enhanced template quality validation and preprocessing"""
        try:
            import cv2
            import numpy as np
            from PIL import Image, ImageEnhance
            import io
            
            # Load and validate image
            pil_image = Image.open(io.BytesIO(image_data))
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # Convert to CV2 format
            cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            height, width = cv_image.shape[:2]
            
            # Calculate image quality metrics
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            
            # 1. Resolution check
            total_pixels = width * height
            is_high_res = total_pixels > 500000  # > 0.5 megapixels
            
            # 2. Contrast analysis
            contrast = gray.std()
            is_good_contrast = contrast > 30
            
            # 3. Blur detection using Laplacian variance
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            is_sharp = blur_score > 100
            
            # 4. Text density estimation
            edges = cv2.Canny(gray, 50, 150)
            text_density = np.sum(edges > 0) / total_pixels
            has_text_content = text_density > 0.02  # At least 2% edge pixels
            
            # 5. Color analysis for template type detection
            hsv = cv2.cvtColor(cv_image, cv2.COLOR_BGR2HSV)
            
            # Detect blue templates (medical letterheads)
            blue_mask = cv2.inRange(hsv, np.array([100, 50, 50]), np.array([130, 255, 255]))
            blue_ratio = np.sum(blue_mask > 0) / total_pixels
            
            # Detect green templates  
            green_mask = cv2.inRange(hsv, np.array([40, 50, 50]), np.array([80, 255, 255]))
            green_ratio = np.sum(green_mask > 0) / total_pixels
            
            # Quality assessment
            quality_score = 0
            quality_issues = []
            
            if is_high_res:
                quality_score += 25
            else:
                quality_issues.append("Low resolution")
                
            if is_good_contrast:
                quality_score += 25
            else:
                quality_issues.append("Poor contrast")
                
            if is_sharp:
                quality_score += 25
            else:
                quality_issues.append("Image blur detected")
                
            if has_text_content:
                quality_score += 25
            else:
                quality_issues.append("Minimal text content")
            
            # Template characteristics
            template_info = {
                'has_blue_elements': blue_ratio > 0.01,  # >1% blue pixels
                'has_green_elements': green_ratio > 0.01,  # >1% green pixels
                'is_colorful': (blue_ratio + green_ratio) > 0.02,
                'estimated_type': 'letterhead' if (blue_ratio > 0.005 or green_ratio > 0.005) else 'form'
            }
            
            return {
                'quality_score': quality_score,
                'quality_issues': quality_issues,
                'is_processable': quality_score >= 50,  # At least 50% quality
                'resolution': f"{width}x{height}",
                'contrast_score': contrast,
                'sharpness_score': blur_score,
                'text_density': text_density,
                'template_info': template_info,
                'preprocessing_needed': quality_score < 75
            }
            
        except Exception as e:
            _logger.error(f"Template quality validation failed: {str(e)}")
            return {
                'quality_score': 0,
                'quality_issues': ['Validation failed'],
                'is_processable': False,
                'preprocessing_needed': True
            }
    
    def _preprocess_image_for_ocr(self, img, quality_results):
        """Preprocess image to improve OCR accuracy"""
        try:
            import cv2
            import numpy as np
            
            processed_img = img.copy()
            
            # 1. Enhance contrast if poor
            if quality_results['contrast_score'] < 40:
                # Convert to LAB color space for better contrast enhancement
                lab = cv2.cvtColor(processed_img, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                
                # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                l = clahe.apply(l)
                
                processed_img = cv2.merge([l, a, b])
                processed_img = cv2.cvtColor(processed_img, cv2.COLOR_LAB2BGR)
            
            # 2. Reduce noise and sharpen if blurry
            if quality_results['sharpness_score'] < 150:
                # Gaussian blur to reduce noise
                processed_img = cv2.GaussianBlur(processed_img, (3, 3), 0)
                
                # Unsharp masking for sharpening
                gaussian = cv2.GaussianBlur(processed_img, (9, 9), 10.0)
                processed_img = cv2.addWeighted(processed_img, 1.5, gaussian, -0.5, 0)
            
            # 3. Ensure minimum resolution for OCR
            height, width = processed_img.shape[:2]
            if height * width < 800000:  # Less than 0.8 megapixels
                # Upscale using cubic interpolation
                scale_factor = (800000 / (height * width)) ** 0.5
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                processed_img = cv2.resize(processed_img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
                
            _logger.info(f"Image preprocessing completed: contrast enhanced, sharpened, "
                        f"resolution: {processed_img.shape[1]}x{processed_img.shape[0]}")
            
            return processed_img
            
        except Exception as e:
            _logger.error(f"Image preprocessing failed: {str(e)}")
            return img  # Return original if preprocessing fails
    
    def action_reanalyze_template(self):
        """Action to manually trigger template re-analysis"""
        self.ensure_one()
        if not self.prescription_template_image:
            raise ValidationError(_('No prescription template image found to analyze'))
        
        self.template_analysis_done = False
        self._analyze_prescription_template()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Template Analysis'),
                'message': _('Template analysis completed successfully. Confidence: %.1f%%') % self.analysis_confidence,
                'type': 'success',
                'sticky': False,
            }
        }
    
    def get_analysis_summary(self):
        """Get human-readable analysis summary with detailed breakdown"""
        self.ensure_one()
        
        if not self.template_analysis_done:
            return _('Template not analyzed yet')
        
        layout_names = {
            'letterhead_top': _('Letterhead at Top'),
            'letterhead_full': _('Full Letterhead (Top + Bottom)'),
            'simple': _('Simple Template'),
            'complex': _('Complex Layout'),
            'unknown': _('Unknown Layout')
        }
        
        layout_name = layout_names.get(self.template_layout_type, _('Unknown'))
        
        summary = _('Layout: %(layout)s, Confidence: %(confidence).1f%%') % {
            'layout': layout_name,
            'confidence': self.analysis_confidence or 0
        }
        
        if self.detected_text_regions:
            try:
                regions = json.loads(self.detected_text_regions)
                header_count = len([r for r in regions if r.get('is_header')])
                footer_count = len([r for r in regions if r.get('is_footer')])
                
                summary += _(', Text Regions: %(total)d (Header: %(header)d, Footer: %(footer)d)') % {
                    'total': len(regions),
                    'header': header_count,
                    'footer': footer_count
                }
                
                # Add drawing area info
                if self.drawing_area_coords:
                    coords = json.loads(self.drawing_area_coords)
                    area_percent = coords.get('height', 0) * 100
                    summary += _(', Drawing Area: %(percent).0f%% height') % {'percent': area_percent}
                    
            except Exception as e:
                _logger.warning(f"Error parsing analysis summary: {e}")
                
        return summary
    
    def action_test_template_analysis(self):
        """Enhanced template analysis test with comprehensive quality assessment"""
        self.ensure_one()
        
        if not self.prescription_template_image:
            raise ValidationError(_('Please upload a prescription template image first'))
        
        try:
            # Step 1: Quality assessment
            image_data = base64.b64decode(self.prescription_template_image)
            quality_results = self._validate_template_quality(image_data)
            
            # Step 2: Force re-analysis
            self.template_analysis_done = False
            self._analyze_prescription_template()
            
            # Step 3: Prepare enhanced analysis report
            report_lines = [
                f"🏥 **ENHANCED TEMPLATE ANALYSIS REPORT**",
                f"Doctor: **{self.name}**",
                f"",
                f"� **QUALITY ASSESSMENT:**",
                f"   • Overall Quality: **{quality_results['quality_score']}%**",
                f"   • Resolution: {quality_results['resolution']} ({quality_results['text_density']:.1%} text density)",
                f"   • Template Type: **{quality_results['template_info']['estimated_type'].title()}**",
                f"   • Contrast Score: {quality_results['contrast_score']:.1f}",
                f"   • Sharpness Score: {quality_results['sharpness_score']:.1f}",
                f"   • Issues: {', '.join(quality_results['quality_issues']) if quality_results['quality_issues'] else '✅ None'}",
                f"",
                f"🔍 **OCR ANALYSIS:**",
                f"   • Layout Detected: **{self.template_layout_type or 'Unknown'}**",
                f"   • Analysis Confidence: **{self.analysis_confidence:.1f}%**",
                f""
            ]
            
            if self.detected_text_regions:
                try:
                    regions = json.loads(self.detected_text_regions)
                    header_regions = [r for r in regions if r.get('is_header')]
                    footer_regions = [r for r in regions if r.get('is_footer')]
                    
                    report_lines.extend([
                        f"📝 **Detected Text Regions**: {len(regions)} total",
                        f"   • Header regions: {len(header_regions)}",
                        f"   • Footer regions: {len(footer_regions)}",
                        f"   • Body regions: {len(regions) - len(header_regions) - len(footer_regions)}",
                        f""
                    ])
                    
                    if header_regions:
                        report_lines.append("🏥 **Header Content**:")
                        for region in header_regions[:5]:  # Show first 5
                            report_lines.append(f"   • '{region['text']}' (confidence: {region['confidence']}%)")
                        if len(header_regions) > 5:
                            report_lines.append(f"   • ... and {len(header_regions) - 5} more")
                        report_lines.append("")
                    
                except Exception as e:
                    report_lines.append(f"❌ Error parsing regions: {e}")
            
            if self.drawing_area_coords:
                try:
                    coords = json.loads(self.drawing_area_coords)
                    report_lines.extend([
                        f"✏️ **OPTIMAL DRAWING AREA**:",
                        f"   • Position: ({coords['x'] * 100:.1f}%, {coords['y'] * 100:.1f}%)",
                        f"   • Size: {coords['width'] * 100:.1f}% × {coords['height'] * 100:.1f}%",
                        f"   • Usable Space: **{(coords['width'] * coords['height']) * 100:.1f}%** of template",
                        f""
                    ])
                except:
                    report_lines.append("❌ Error parsing drawing area coordinates")
            
            # Add recommendations
            report_lines.extend([
                "💡 **RECOMMENDATIONS:**"
            ])
            
            if quality_results['quality_score'] < 70:
                report_lines.append(f"   • ⚠️ Consider higher resolution template (current: {quality_results['resolution']})")
            if len(json.loads(self.detected_text_regions or '[]')) == 0:
                report_lines.append("   • ⚠️ No text detected - manual drawing area setup may be needed")
            if quality_results['preprocessing_needed']:
                report_lines.append("   • ✅ Image enhancement was applied for better analysis")
            if self.analysis_confidence > 80:
                report_lines.append("   • ✅ Excellent analysis - template ready for use!")
            elif self.analysis_confidence > 60:
                report_lines.append("   • ✅ Good analysis - template should work well")
            else:
                report_lines.append("   • ⚠️ Consider manual adjustment of drawing area")
        
            report = "\n".join(report_lines)
            success_type = 'success' if self.analysis_confidence > 60 else 'warning'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Enhanced Template Analysis Complete'),
                    'message': report,
                    'type': success_type,
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Enhanced template analysis failed: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Template Analysis Failed'),
                    'message': f'Error during enhanced analysis: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
    
    def validate_drawing_coordinates(self, x, y, width, height):
        """Validate if drawing coordinates are within allowed area"""
        self.ensure_one()
        
        if not self.drawing_area_coords:
            return True  # Allow if no restrictions
        
        try:
            allowed_area = json.loads(self.drawing_area_coords)
            
            # Check if the drawing coordinates overlap with allowed area
            allowed_x1 = allowed_area['x']
            allowed_y1 = allowed_area['y']
            allowed_x2 = allowed_area['x'] + allowed_area['width']
            allowed_y2 = allowed_area['y'] + allowed_area['height']
            
            drawing_x1 = x
            drawing_y1 = y
            drawing_x2 = x + width
            drawing_y2 = y + height
            
            # Check if drawing is completely within allowed area
            return (drawing_x1 >= allowed_x1 and drawing_y1 >= allowed_y1 and
                    drawing_x2 <= allowed_x2 and drawing_y2 <= allowed_y2)
        except:
            return True  # Allow if validation fails
    
    def get_drawing_area_coords(self):
        """Get comprehensive drawing area data for frontend"""
        self.ensure_one()
        if not self.template_analysis_done:
            self._analyze_prescription_template()
        
        result = {
            'drawing_area': {'x': 0.1, 'y': 0.2, 'width': 0.8, 'height': 0.6},
            'restricted_areas': [],
            'confidence': 50.0,
            'layout_type': 'simple'
        }
        
        try:
            if self.drawing_area_coords:
                result['drawing_area'] = json.loads(self.drawing_area_coords)
            
            if self.header_footer_coords:
                header_footer = json.loads(self.header_footer_coords)
                result['restricted_areas'] = [
                    {'type': 'header', **header_footer.get('header', {})},
                    {'type': 'footer', **header_footer.get('footer', {})}
                ]
            
            result['confidence'] = self.analysis_confidence or 50.0
            result['layout_type'] = self.template_layout_type or 'simple'
            
            # Add text regions for advanced restriction
            if self.detected_text_regions:
                text_regions = json.loads(self.detected_text_regions)
                # Add high-confidence text regions as restricted areas
                for region in text_regions:
                    if region.get('confidence', 0) > 70:
                        result['restricted_areas'].append({
                            'type': 'text',
                            'x': region['x'],
                            'y': region['y'], 
                            'width': region['width'],
                            'height': region['height'],
                            'text': region.get('text', '')
                        })
        except Exception as e:
            _logger.warning(f"Error loading drawing area data for {self.name}: {str(e)}")
        
        return result

