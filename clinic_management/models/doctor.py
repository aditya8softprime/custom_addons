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
    shift_type = fields.Selection([('morning', 'Morning'), ('evening', 'Evening')], string="Shift Type", required=True)
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
        slot_number = 1
        
        while current < end:
            start_min = current
            end_min = min(current + self.slot_duration, end)

            start_time_float = start_min / 60
            end_time_float = end_min / 60
            
            start_label = f"{int(start_min//60):02d}:{int(start_min%60):02d}"
            end_label = f"{int(end_min//60):02d}:{int(end_min%60):02d}"
            slot_label = f"{start_label} - {end_label}"
            
            # Generate slot number based on clinic.days code and shift
            day_code = (self.day_id.code or '').upper()
            shift_code = 'M' if self.shift_type == 'morning' else 'E'
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
    # Doctor-specific prescription template image for canvas background
    prescription_template_image = fields.Binary(
        string='Prescription Template Image',
        attachment=True,
        help='Upload a background image for prescriptions. This will auto-load on appointments when this doctor is selected.'
    )
    prescription_template_filename = fields.Char(string='Template Filename')
    
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
        # Create slots for each doctor
        for doctor in doctors:
            doctor._create_slots()
        return doctors
    
    def write(self, vals):
        res = super(ClinicDoctor, self).write(vals)
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
            slot_number = 1
            
            # Morning shift slots
            if self.morning_shift and self.morning_start_time and self.morning_end_time:
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
            
            # Reset slot number for evening shift
            slot_number = 1
            
            # Evening shift slots
            if self.evening_shift and self.evening_start_time and self.evening_end_time:
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
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise ValueError("Could not decode image")
                
            height, width = img.shape[:2]
            _logger.info(f"Analyzing template for {self.name}: {width}x{height} pixels")
            
            # Perform comprehensive analysis
            analysis_results = self._perform_comprehensive_analysis(img)
            
            # Extract results
            drawing_coords = analysis_results['drawing_area']
            header_footer = analysis_results['header_footer']
            text_regions = analysis_results['text_regions']
            confidence = analysis_results['confidence']
            layout_type = analysis_results['layout_type']
            
            # Store results
            self.drawing_area_coords = json.dumps(drawing_coords)
            self.header_footer_coords = json.dumps(header_footer)
            self.detected_text_regions = json.dumps(text_regions)
            self.analysis_confidence = confidence
            self.template_layout_type = layout_type
            self.template_analysis_done = True
            
            _logger.info(f"Template analysis completed for {self.name}. "
                        f"Layout: {layout_type}, Confidence: {confidence:.1f}%, "
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
        """Use Tesseract OCR to detect text regions"""
        try:
            # Convert OpenCV image to PIL
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)
            
            # Get detailed OCR data
            ocr_data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT, lang='eng+hin')
            
            text_regions = []
            height, width = img.shape[:2]
            
            # Process OCR results
            for i in range(len(ocr_data['text'])):
                confidence = int(ocr_data['conf'][i])
                text = ocr_data['text'][i].strip()
                
                # Filter out low confidence and empty text
                if confidence > 30 and text:
                    x = ocr_data['left'][i]
                    y = ocr_data['top'][i]
                    w = ocr_data['width'][i]
                    h = ocr_data['height'][i]
                    
                    # Convert to relative coordinates
                    region = {
                        'text': text,
                        'confidence': confidence,
                        'x': x / width,
                        'y': y / height,
                        'width': w / width,
                        'height': h / height,
                        'is_header': y < height * 0.25,  # Top 25% likely header
                        'is_footer': y > height * 0.75,  # Bottom 25% likely footer
                    }
                    text_regions.append(region)
            
            _logger.info(f"OCR detected {len(text_regions)} text regions")
            return text_regions
            
        except Exception as e:
            _logger.warning(f"OCR text detection failed: {str(e)}")
            return []
    
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
        """Combine OCR and computer vision results to determine layout"""
        
        # Categorize text regions
        header_regions = [r for r in text_regions if r['is_header']]
        footer_regions = [r for r in text_regions if r['is_footer']]
        body_regions = [r for r in text_regions if not r['is_header'] and not r['is_footer']]
        
        # Calculate header and footer boundaries
        header_bottom = 0.15  # Default
        footer_top = 0.85     # Default
        
        if header_regions:
            header_bottom = max(r['y'] + r['height'] for r in header_regions)
            header_bottom = min(header_bottom + 0.05, 0.3)  # Add padding, max 30%
            
        if footer_regions:
            footer_top = min(r['y'] for r in footer_regions)
            footer_top = max(footer_top - 0.05, 0.7)  # Add padding, min 70%
        
        # Determine layout type
        layout_type = self._determine_layout_type(header_regions, footer_regions, cv_analysis)
        
        # Calculate confidence based on OCR quality and structure detection
        confidence = self._calculate_analysis_confidence(text_regions, cv_analysis)
        
        # Define safe drawing area
        margin_x = 0.08  # 8% horizontal margin
        margin_y = 0.03  # 3% vertical margin
        
        drawing_x = margin_x
        drawing_y = header_bottom + margin_y
        drawing_width = 1.0 - (2 * margin_x)
        drawing_height = footer_top - drawing_y - margin_y
        
        # Ensure minimum drawing area
        if drawing_height < 0.4:  # Minimum 40% height
            drawing_y = 0.2
            drawing_height = 0.6
        
        drawing_coords = {
            'x': drawing_x,
            'y': drawing_y,
            'width': drawing_width,
            'height': drawing_height
        }
        
        header_footer_coords = {
            'header': {'y': 0, 'height': header_bottom},
            'footer': {'y': footer_top, 'height': 1.0 - footer_top}
        }
        
        return {
            'drawing_area': drawing_coords,
            'header_footer': header_footer_coords,
            'text_regions': text_regions,
            'confidence': confidence,
            'layout_type': layout_type
        }
    
    def _determine_layout_type(self, header_regions, footer_regions, cv_analysis):
        """Determine the type of prescription template layout"""
        
        has_substantial_header = len(header_regions) > 2 or any(r['height'] > 0.08 for r in header_regions)
        has_substantial_footer = len(footer_regions) > 1 or any(r['height'] > 0.05 for r in footer_regions)
        
        text_block_count = len(cv_analysis['text_blocks'])
        
        if has_substantial_header and has_substantial_footer:
            return 'letterhead_full'
        elif has_substantial_header:
            return 'letterhead_top'
        elif text_block_count > 10:
            return 'complex'
        elif text_block_count < 3:
            return 'simple'
        else:
            return 'unknown'
    
    def _calculate_analysis_confidence(self, text_regions, cv_analysis):
        """Calculate confidence score for the analysis"""
        confidence = 50.0  # Base confidence
        
        # OCR contribution (30% weight)
        if text_regions:
            avg_ocr_confidence = sum(r['confidence'] for r in text_regions) / len(text_regions)
            ocr_score = min(avg_ocr_confidence, 90) * 0.3
            confidence += ocr_score * 0.5
        
        # Structural analysis contribution (20% weight)
        text_block_count = len(cv_analysis['text_blocks'])
        if text_block_count > 0:
            structure_score = min(text_block_count * 5, 80) * 0.2
            confidence += structure_score * 0.5
        
        # Boundary detection confidence (20% weight)
        if text_regions:
            header_regions = [r for r in text_regions if r['is_header']]
            footer_regions = [r for r in text_regions if r['is_footer']]
            
            if header_regions or footer_regions:
                boundary_score = 80 * 0.2
                confidence += boundary_score * 0.5
        
        return min(confidence, 95.0)  # Cap at 95%
    
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
        """Get human-readable analysis summary"""
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
                summary += _(', Text Regions: %(count)d') % {'count': len(regions)}
            except:
                pass
                
        return summary
    
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

