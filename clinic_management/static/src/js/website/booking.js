/** @odoo-module **/

import { Component, useState, onMounted, mount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

/**
 * Clinic Booking Form Component
 */
class ClinicBookingForm extends Component {
    setup() {
        // Set up reactive state
        this.state = useState({
            doctorId: '',
            appointmentDate: '',
            showSlotDiv: false,
            slots: [],
            selectedSlot: '',
            submitting: false,
            errorMessage: '',
        });
        
        // Handle mounted lifecycle
        onMounted(() => this.onMounted());
    }
    
    /**
     * Component mounted
     */
    onMounted() {
        // Get initial values
        const doctorSelect = document.getElementById('doctor_id');
        const dateInput = document.getElementById('appointment_date');
        const form = document.querySelector('.js_clinic_booking_form');
        
        if (doctorSelect) {
            doctorSelect.addEventListener('change', this.onDoctorChange.bind(this));
            this.state.doctorId = doctorSelect.value;
        }
        
        if (dateInput) {
            dateInput.addEventListener('change', this.onDateChange.bind(this));
            this.state.appointmentDate = dateInput.value;
        }
        
        if (form) {
            // Use handleSubmit instead of onFormSubmit for AJAX submission
            form.addEventListener('submit', this.handleSubmit.bind(this));
            this.submitBtn = form.querySelector('button[type="submit"]');
        }
        
        this.updateSlotDiv();
    }
    
    /**
     * Handles doctor selection change
     */
    onDoctorChange(event) {
        this.state.doctorId = event.target.value;
        this.updateAvailableSlots();
    }
    
    /**
     * Handles date selection change
     */
    onDateChange(event) {
        this.state.appointmentDate = event.target.value;
        this.updateAvailableSlots();
    }
    
    /**
     * Handle form submission via AJAX
     * @param {Event} event The form submission event
     */
    async handleSubmit(event) {
        event.preventDefault();
        console.log("Form submission started");
        
        // Validate the form
        if (!this.validateForm()) {
            console.log("Form validation failed");
            return;
        }
        
        const form = event.target;
        const formData = new FormData(form);
        
        // Log form data for debugging
        for (const [key, value] of formData.entries()) {
            console.log(`${key}: ${value}`);
        }
        
        try {
            // Disable submit button and show loading state
            if (this.submitBtn) {
                this.submitBtn.disabled = true;
                this.submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Submitting...';
            }
            
            // Send AJAX request
            const response = await fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });
            
            console.log("Response status:", response.status);
            console.log("Response headers:", response.headers);
            
            let result;
            
            // Parse the response based on content type
            const contentType = response.headers.get('content-type');
            console.log("Content type:", contentType);
            
            if (contentType && contentType.includes('application/json')) {
                const responseText = await response.text();
                console.log("Response text:", responseText);
                try {
                    result = JSON.parse(responseText);
                } catch (e) {
                    console.error('Error parsing JSON response:', e, responseText);
                    result = { success: false, error: 'Invalid response from server' };
                }
            } else {
                // Handle non-JSON response (likely an error page)
                const responseText = await response.text();
                console.warn('Received non-JSON response');
                console.log("Response text sample:", responseText.substring(0, 200) + "...");
                result = { 
                    success: false, 
                    error: 'Server returned an unexpected response. Please try again.' 
                };
            }
            
            if (result.success) {
                // Show success message
                this.showMessage(result.message || 'Appointment booked successfully!', 'success');
                
                // Reset form
                form.reset();
                this.resetValidationStates();
                
                // Reset state
                this.state.doctorId = '';
                this.state.appointmentDate = '';
                
                // Hide slot div
                const slotDiv = document.getElementById('slot_div');
                if (slotDiv) {
                    slotDiv.style.display = 'none';
                }
                
                // Redirect if provided
                if (result.redirect_url) {
                    setTimeout(() => {
                        window.location.href = result.redirect_url;
                    }, 1500);
                }
            } else {
                // Show error message
                this.showMessage(result.error || 'Failed to book appointment. Please try again.', 'danger');
                
                // Handle field-specific errors
                if (result.field_errors) {
                    Object.entries(result.field_errors).forEach(([field, message]) => {
                        const element = document.getElementById(field);
                        if (element) {
                            this.markFieldInvalid(element, message);
                        }
                    });
                }
            }
        } catch (error) {
            console.error('Error submitting form:', error);
            this.showMessage('An error occurred while submitting the form. Please try again.', 'danger');
        } finally {
            // Re-enable submit button
            if (this.submitBtn) {
                this.submitBtn.disabled = false;
                this.submitBtn.innerHTML = 'Book Appointment';
            }
        }
    }
    
    /**
     * Validates the form before submission
     * @returns {boolean} Whether the form is valid
     */
    validateForm() {
        // Reset validation states
        this.resetValidationStates();
        
        const doctorSelect = document.getElementById('doctor_id');
        const dateInput = document.getElementById('appointment_date');
        const slotSelect = document.getElementById('slot_id');
        const slotDiv = document.getElementById('slot_div');
        const nameInput = document.getElementById('patient_name');
        const phoneInput = document.getElementById('phone');
        const ageInput = document.getElementById('age');
        const genderSelect = document.getElementById('gender');
        const symptomTextarea = document.getElementById('symptom');
        
        let isValid = true;
        
        // Validate required fields
        if (!nameInput || !nameInput.value.trim()) {
            isValid = false;
            this.markFieldInvalid(nameInput, 'Please enter your name');
        }
        
        if (!phoneInput || !phoneInput.value.trim()) {
            isValid = false;
            this.markFieldInvalid(phoneInput, 'Please enter your phone number');
        }
        
        if (!ageInput || !ageInput.value.trim()) {
            isValid = false;
            this.markFieldInvalid(ageInput, 'Please enter your age');
        }
        
        if (!genderSelect || !genderSelect.value) {
            isValid = false;
            this.markFieldInvalid(genderSelect, 'Please select your gender');
        }
        
        // Validate symptom field
        const symptomField = document.getElementById('symptom');
        if (!symptomField || !symptomField.value.trim()) {
            isValid = false;
            this.markFieldInvalid(symptomField, 'Please describe your symptoms or reason for visit');
            console.log("Symptom validation failed");
        }
        
        if (!doctorSelect || !doctorSelect.value) {
            isValid = false;
            this.markFieldInvalid(doctorSelect, 'Please select a doctor');
        }
        
        if (!dateInput || !dateInput.value) {
            isValid = false;
            this.markFieldInvalid(dateInput, 'Please select an appointment date');
        }
        
        // Debug logging
        console.log("Doctor ID:", doctorId);
        console.log("Date:", dateInput.value);
        console.log("Slot ID:", slotSelect ? slotSelect.value : "No slot select");
        console.log("Slot div visible:", slotDiv ? slotDiv.style.display : "No slot div");
        
        // Validate slot only if doctor and date are selected and slots are visible
        if (doctorSelect && doctorSelect.value && 
            dateInput && dateInput.value && 
            slotDiv && slotDiv.style.display !== 'none' && 
            (!slotSelect || !slotSelect.value)) {
            isValid = false;
            this.markFieldInvalid(slotSelect, 'Please select an available time slot');
            console.log("Slot validation failed");
        }
        
        if (!isValid) {
            this.showMessage('Please fill in all required fields', 'danger');
        }
        
        return isValid;
    }
    
    /**
     * Resets validation states for all form fields
     */
    resetValidationStates() {
        const form = document.querySelector('.js_clinic_booking_form');
        if (!form) return;
        
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.classList.remove('is-invalid');
            
            // Remove any existing feedback elements
            const feedback = input.parentNode.querySelector('.invalid-feedback');
            if (feedback) {
                feedback.remove();
            }
        });
    }
    
    /**
     * Marks a field as invalid with error message
     */
    markFieldInvalid(field, message) {
        if (!field) return;
        
        field.classList.add('is-invalid');
        
        // Add error message
        let feedback = field.parentNode.querySelector('.invalid-feedback');
        if (!feedback) {
            feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            field.parentNode.appendChild(feedback);
        }
        
        feedback.textContent = message;
    }
    
    /**
     * Updates slot div visibility
     */
    updateSlotDiv() {
        const slotDiv = document.getElementById('slot_div');
        if (slotDiv) {
            if (this.state.doctorId && this.state.appointmentDate) {
                slotDiv.style.display = 'block';
            } else {
                slotDiv.style.display = 'none';
            }
        }
    }
    
    /**
     * Fetches and updates available slots
     */
    async updateAvailableSlots() {
        const { doctorId, appointmentDate } = this.state;
        const slotDiv = document.getElementById('slot_div');
        const slotSelect = document.getElementById('slot_id');
        
        if (!doctorId || !appointmentDate || !slotDiv || !slotSelect) {
            if (slotDiv) slotDiv.style.display = 'none';
            return;
        }
        
        try {
            // Show loading indicator
            slotDiv.style.display = 'block';
            slotSelect.innerHTML = '<option value="">Loading time slots...</option>';
            slotSelect.disabled = true;
            
            const result = await rpc('/clinic/booking/slots', {
                doctor_id: parseInt(doctorId),
                date_str: appointmentDate,
            });
            
            // Clear previous options and remove validation styling
            slotSelect.innerHTML = '';
            slotSelect.classList.remove('is-invalid');
            slotSelect.disabled = false;
            
            // Add default option
            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.text = 'Select Time Slot';
            slotSelect.appendChild(defaultOption);
            
            // Check if request was successful
            if (!result.success) {
                console.error("Slot fetch error:", result.error);
                const errorOption = document.createElement('option');
                errorOption.value = '';
                errorOption.text = 'Error loading slots';
                errorOption.disabled = true;
                slotSelect.appendChild(errorOption);
                
                slotDiv.style.display = 'block'; // Still show the dropdown with error
                this.showMessage(result.error || 'Error loading available slots. Please try again.', 'danger');
                return;
            }
            
            // Handle no available slots
            if (!result.slots || result.slots.length === 0) {
                const noSlotsOption = document.createElement('option');
                noSlotsOption.value = '';
                noSlotsOption.text = 'No available slots';
                noSlotsOption.disabled = true;
                slotSelect.appendChild(noSlotsOption);
                
                slotDiv.style.display = 'block'; // Still show the dropdown but with no slots
                this.showMessage(result.error || 'No available slots for this date. Please select another date.', 'warning');
                return;
            }
            
            // Add new slot options
            if (result.slots && result.slots.length > 0) {
                result.slots.forEach(slot => {
                    const startTime = this.formatTime(slot.start_time);
                    const endTime = this.formatTime(slot.end_time);
                    let text = `${startTime} - ${endTime}`;
                    
                    if (slot.slot_number) {
                        text += ` (Slot ${slot.slot_number})`;
                    }
                    
                    const option = document.createElement('option');
                    option.value = slot.id;
                    option.text = text;
                    slotSelect.appendChild(option);
                });
                
                // If there's only one slot, select it automatically
                if (result.slots.length === 1) {
                    slotSelect.value = result.slots[0].id;
                    console.log("Auto-selected slot:", result.slots[0].id);
                }
            }
            
            slotDiv.style.display = 'block';
            
        } catch (error) {
            console.error('Error fetching slots:', error);
            if (slotDiv) slotDiv.style.display = 'block'; // Show the div even with error
            if (slotSelect) {
                slotSelect.innerHTML = '<option value="">Error loading slots</option>';
                slotSelect.disabled = false;
            }
            this.showMessage('Error fetching available slots. Please try again.', 'danger');
        }
    }
    
    /**
     * Shows a message to the user
     */
    showMessage(message, type = 'warning') {
        // Create or find message div
        let messageContainer = document.getElementById('booking_form_message');
        if (!messageContainer) {
            messageContainer = document.createElement('div');
            messageContainer.id = 'booking_form_message';
            messageContainer.className = 'mt-3 mb-4';
            
            const form = document.querySelector('.js_clinic_booking_form');
            if (form) {
                form.parentNode.insertBefore(messageContainer, form);
            }
        }
        
        // Set message with Bootstrap 5 compatible markup
        messageContainer.innerHTML = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        
        // Scroll to message
        messageContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            const alert = messageContainer.querySelector('.alert');
            if (alert) {
                if (typeof bootstrap !== 'undefined' && bootstrap.Alert) {
                    // Use Bootstrap 5 dismiss if available
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                } else {
                    // Fallback to manual removal
                    alert.classList.remove('show');
                    setTimeout(() => {
                        if (messageContainer.parentNode) {
                            messageContainer.innerHTML = '';
                        }
                    }, 500);
                }
            }
        }, 5000);
    }
    
    /**
     * Formats a float time value to HH:MM format
     */
    formatTime(timeFloat) {
        const hours = Math.floor(timeFloat);
        const minutes = Math.floor((timeFloat - hours) * 60);
        return `${hours < 10 ? '0' : ''}${hours}:${minutes < 10 ? '0' : ''}${minutes}`;
    }
}

// Define the template for the component
ClinicBookingForm.template = "clinic_management.ClinicBookingForm";

// Function to setup the booking form
function setupClinicBookingForm() {
    const formElements = document.querySelectorAll('.js_clinic_booking_form');
    
    if (formElements.length > 0) {
        // For each form element on the page
        formElements.forEach(formElement => {
            // Create a root target next to the form
            const target = document.createElement('div');
            target.className = 'clinic-booking-form-root';
            formElement.parentNode.insertBefore(target, formElement.nextSibling);
            
            // Mount the component to the target
            mount(ClinicBookingForm, target);
        });
    }
}

// Register for website initialization
document.addEventListener('DOMContentLoaded', () => {
    setupClinicBookingForm();
});

// Export the component
export default ClinicBookingForm;
