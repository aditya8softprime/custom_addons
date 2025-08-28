/** @odoo-module **/

import { Component, useState, onMounted, mount } from "@odoo/owl";

/**
 * Doctor Detail Component
 */
class DoctorDetail extends Component {
    setup() {
        // Set up reactive state
        this.state = useState({
            doctor: this.props.doctor || {},
        });
        
        // Handle mounted lifecycle
        onMounted(() => this.onMounted());
    }
    
    /**
     * Component mounted
     */
    onMounted() {
        // Additional initialization if needed
    }
}

// Define the template for the component
DoctorDetail.template = "clinic_management.DoctorDetail";

// Props definition
DoctorDetail.props = {
    doctor: { type: Object, optional: true },
};

// Function to setup the doctor detail component
function setupDoctorDetail() {
    const doctorDetailElement = document.querySelector('.js_doctor_detail');
    
    if (doctorDetailElement) {
        // Create a root target for the component
        const target = document.createElement('div');
        target.className = 'doctor-detail-root';
        doctorDetailElement.parentNode.insertBefore(target, doctorDetailElement.nextSibling);
        
        // Get doctor data from the page
        const doctorData = window.doctor_data || {};
        
        // Mount the component to the target
        mount(DoctorDetail, target, { doctor: doctorData });
    }
}

// Register for website initialization
document.addEventListener('DOMContentLoaded', () => {
    setupDoctorDetail();
});

// Export the component
export default DoctorDetail;
