/** @odoo-module **/

import { Component, useState, onMounted, mount } from "@odoo/owl";

/**
 * Clinic Services Component
 */
class ClinicServices extends Component {
    setup() {
        // Set up reactive state
        this.state = useState({
            services: this.props.services || [],
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
ClinicServices.template = "clinic_management.ClinicServices";

// Props definition
ClinicServices.props = {
    services: { type: Array, optional: true },
};

// Function to setup the services component
function setupClinicServices() {
    const servicesElement = document.querySelector('.js_clinic_services');
    
    if (servicesElement) {
        // Create a root target for the component
        const target = document.createElement('div');
        target.className = 'clinic-services-root';
        servicesElement.parentNode.insertBefore(target, servicesElement.nextSibling);
        
        // Get services data from the page
        const servicesData = window.services_data || [];
        
        // Mount the component to the target
        mount(ClinicServices, target, { services: servicesData });
    }
}

// Register for website initialization
document.addEventListener('DOMContentLoaded', () => {
    setupClinicServices();
});

// Export the component
export default ClinicServices;
