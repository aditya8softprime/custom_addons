/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onMounted } from "@odoo/owl";


const actionRegistry = registry.category("actions");

class AppointmentDashboard extends Component {
    setup() {
        super.setup();
        this.orm = useService('orm');
        this.actionManager = useService('action');

        // Initialize state with today's filter as default
        const initialState = {
            total_appointments: 0,
            total_draft: 0,
            total_confirmed: 0,
            total_patient_in: 0,
            total_in_consultation: 0,
            total_completed: 0,
            total_no_show: 0,
            total_cancelled: 0,
            total_rescheduled: 0,
            total_revenue: 0,
            total_prescriptions: 0,
            total_lab_tests: 0,
            doctor_id: null,
            doctors: [],
            doctors_data: [],
            time_filter: 'today',  // Default to today's filter
            appointment_type: null,  // New appointment type filter
            active_tab: 'overview',
            records: [],
            current_page: 1,
            records_per_page: 15,
            total_records: 0,
            selected_state: null,
            selected_date: null,
        };

        this.state = useState(initialState);

        // Fetch data on component mount
        onWillStart(async () => {
            await this._fetch_doctors();
            await this._fetch_data();
            await this._fetch_doctors_data();
        });

        // Initialize chart after component is mounted
        onMounted(() => {
            if (this.state.active_tab === 'overview') {
                this._loadChartJsAndRender();
            }
        });
    }

    async _fetch_doctors() {
        try {
            const domain = [];
            const fields = ['name', 'id'];
            const doctors = await this.orm.call("clinic.doctor", "search_read", [domain, fields]);
            this.state.doctors = doctors;
        } catch (error) {
            console.error('Error fetching doctors:', error);
            this.state.doctors = [];
        }
    }

    async _fetch_doctors_data() {
        try {
            console.log('Fetching doctors data with filters:', {
                doctor_id: this.state.doctor_id,
                time_filter: this.state.time_filter,
                selected_date: this.state.selected_date
            });
            
            const result = await this.orm.call("clinic.appointment", "get_doctors_slots_data", [
                this.state.doctor_id,
                this.state.time_filter,
                this.state.selected_date
            ]);
            
            console.log('Doctors data received:', result);
            console.log('Number of doctors:', result.doctors_data?.length || 0);
            
            this.state.doctors_data = result.doctors_data || [];
        } catch (error) {
            console.error('Error fetching doctors data:', error);
            this.state.doctors_data = [];
        }
    }

    async _fetch_data() {
        try {
            // Fetch dashboard tile data
            const result = await this.orm.call("clinic.appointment", "get_appointment_dashboard_data", [
                this.state.doctor_id, this.state.time_filter, this.state.selected_date, this.state.appointment_type
            ]);
            
            console.log('Dashboard data received:', result);
            console.log('Current doctor_id:', this.state.doctor_id);
            console.log('Current time_filter:', this.state.time_filter);
            
            Object.assign(this.state, result);
            
            console.log('State after assignment:', {
                total_appointments: this.state.total_appointments,
                total_confirmed: this.state.total_confirmed,
                total_completed: this.state.total_completed,
                total_draft: this.state.total_draft
            });

            // Fetch list data for the table
            await this._fetch_list_data();

            // Update charts
            if (this.state.active_tab === 'overview') {
                this._loadChartJsAndRender();
            }
        } catch (error) {
            console.error('Error fetching dashboard data:', error);
        }
    }

    async _loadChartJsAndRender() {
        // Check if Chart.js is already loaded
        if (window.Chart) {
            this._renderCharts();
            return;
        }

        // Load Chart.js from CDN
        try {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
            script.onload = () => {
                this._renderCharts();
            };
            document.head.appendChild(script);
        } catch (error) {
            console.error('Failed to load Chart.js:', error);
        }
    }

    async _fetch_list_data() {
        try {
            const offset = (this.state.current_page - 1) * this.state.records_per_page;
            const result = await this.orm.call("clinic.appointment", "get_appointment_list_data", [
                this.state.doctor_id,
                this.state.time_filter,
                this.state.selected_state,
                offset,
                this.state.records_per_page,
                this.state.selected_date,
                this.state.appointment_type
            ]);
            
            this.state.total_records = result.total_records;
            this.state.records = result.records;
        } catch (error) {
            console.error('Error fetching list data:', error);
            this.state.records = [];
            this.state.total_records = 0;
        }
    }

    _renderCharts() {
        // Add a small delay to ensure DOM elements are ready
        setTimeout(() => {
            this._renderPieChart();
            this._renderBarChart();
        }, 100);
    }

    _renderPieChart() {
        const canvas = document.getElementById('appointmentPieChart');
        if (!canvas) {
            console.error('Canvas element with id "appointmentPieChart" not found');
            return;
        }
        
        const ctx = canvas.getContext('2d');
        if (!ctx) {
            console.error('Could not get 2D context from canvas');
            return;
        }

        if (!window.Chart) {
            console.error('Chart.js library not loaded');
            return;
        }

        if (this.pieChart) {
            this.pieChart.destroy();
        }

        console.log('Rendering pie chart with data:', {
            confirmed: this.state.total_confirmed,
            completed: this.state.total_completed,
            patient_in: this.state.total_patient_in,
            in_consultation: this.state.total_in_consultation,
            no_show: this.state.total_no_show,
            cancelled: this.state.total_cancelled,
            draft: this.state.total_draft
        });

        this.pieChart = new window.Chart(ctx, {
            type: 'pie',
            data: {
                labels: ['Confirmed', 'Completed', 'Patient In', 'In Consultation', 'No Show', 'Cancelled', 'Draft'],
                datasets: [{
                    data: [
                        this.state.total_confirmed,
                        this.state.total_completed,
                        this.state.total_patient_in,
                        this.state.total_in_consultation,
                        this.state.total_no_show,
                        this.state.total_cancelled,
                        this.state.total_draft
                    ],
                    backgroundColor: [
                        '#007bff',
                        '#28a745',
                        '#17a2b8',
                        '#ffc107',
                        '#fd7e14',
                        '#dc3545',
                        '#6c757d'
                    ],
                    borderColor: '#ffffff',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            font: { size: 14, weight: 'bold' },
                            color: '#333',
                        }
                    },
                    tooltip: {
                        backgroundColor: '#fff',
                        titleColor: '#222',
                        bodyColor: '#333',
                        borderColor: '#eee',
                        borderWidth: 1
                    }
                }
            }
        });
    }

    _renderBarChart() {
        const canvas = document.getElementById('appointmentBarChart');
        if (!canvas) {
            console.error('Canvas element with id "appointmentBarChart" not found');
            return;
        }
        
        const ctx = canvas.getContext('2d');
        if (!ctx) {
            console.error('Could not get 2D context from canvas');
            return;
        }

        if (!window.Chart) {
            console.error('Chart.js library not loaded');
            return;
        }

        if (this.barChart) {
            this.barChart.destroy();
        }

        console.log('Rendering bar chart with data:', {
            confirmed: this.state.total_confirmed,
            completed: this.state.total_completed,
            patient_in: this.state.total_patient_in,
            in_consultation: this.state.total_in_consultation,
            no_show: this.state.total_no_show,
            cancelled: this.state.total_cancelled,
            draft: this.state.total_draft
        });

        this.barChart = new window.Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Confirmed', 'Completed', 'Checked In', 'In Consultation', 'No Show', 'Cancelled', 'Draft'],
                datasets: [{
                    label: 'Appointments',
                    data: [
                        this.state.total_confirmed,
                        this.state.total_completed,
                        this.state.total_patient_in,
                        this.state.total_in_consultation,
                        this.state.total_no_show,
                        this.state.total_cancelled,
                        this.state.total_draft
                    ],
                    backgroundColor: [
                        'rgba(0,123,255,0.7)',
                        'rgba(40,167,69,0.7)',
                        'rgba(23,162,184,0.7)',
                        'rgba(255,193,7,0.7)',
                        'rgba(253,126,20,0.7)',
                        'rgba(220,53,69,0.7)',
                        'rgba(108,117,125,0.7)'
                    ],
                    borderColor: [
                        '#007bff',
                        '#28a745',
                        '#17a2b8',
                        '#ffc107',
                        '#fd7e14',
                        '#dc3545',
                        '#6c757d'
                    ],
                    borderWidth: 2,
                    borderRadius: 8,
                    maxBarThickness: 40
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#fff',
                        titleColor: '#222',
                        bodyColor: '#333',
                        borderColor: '#eee',
                        borderWidth: 1
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.07)' },
                        ticks: { color: '#333', font: { size: 13 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#333', font: { size: 13 } }
                    }
                }
            }
        });
    }

    // Event handlers
    on_time_filter_change(filter) {
        if (filter === 'till_now') {
            // All Time button - set to null to show all records
            this.state.time_filter = null;
        } else {
            // Toggle between selected filter and null
            this.state.time_filter = this.state.time_filter === filter ? null : filter;
        }
        this.state.current_page = 1;
        this._fetch_data();
        
        // Refresh doctors data if doctors tab is active
        if (this.state.active_tab === 'doctors') {
            this._fetch_doctors_data();
        }
        // Refresh list data if list tab is active
        if (this.state.active_tab === 'list') {
            this._fetch_list_data();
        }
    }

    on_doctor_change(event) {
        this.state.doctor_id = event.target.value ? parseInt(event.target.value, 10) : null;
        this.state.current_page = 1;
        this._fetch_data();
        
        // Refresh doctors data if doctors tab is active
        if (this.state.active_tab === 'doctors') {
            this._fetch_doctors_data();
        }
        // Refresh list data if list tab is active
        if (this.state.active_tab === 'list') {
            this._fetch_list_data();
        }
    }

    on_date_change(event) {
        this.state.selected_date = event.target.value;
        this.state.time_filter = 'custom_date';  // Set special filter for custom date
        this.state.current_page = 1;
        this._fetch_data();
        
        // Refresh doctors data if doctors tab is active
        if (this.state.active_tab === 'doctors') {
            this._fetch_doctors_data();
        }
        
        // Refresh list data if list tab is active
        if (this.state.active_tab === 'list') {
            this._fetch_list_data();
        }
    }

    clear_date_filter() {
        this.state.selected_date = null;
        this.state.time_filter = null;
        this.state.current_page = 1;
        this._fetch_data();
        
        // Refresh doctors data if doctors tab is active
        if (this.state.active_tab === 'doctors') {
            this._fetch_doctors_data();
        }
        
        // Refresh list data if list tab is active
        if (this.state.active_tab === 'list') {
            this._fetch_list_data();
        }
    }

    on_appointment_type_change(event) {
        this.state.appointment_type = event.target.value || null;
        this.state.current_page = 1;
        // Only fetch overview data, not doctors data as per requirement
        this._fetch_data();
        
        // Refresh list data if list tab is active
        if (this.state.active_tab === 'list') {
            this._fetch_list_data();
        }
    }

    async _open_list_view(state) {
        this.state.selected_state = state;
        this.state.current_page = 1;
        await this._fetch_list_data();
    }

    set_active_tab(tab) {
        this.state.active_tab = tab;
        this.state.selected_state = null;
        this.state.current_page = 1;
        
        if (tab === 'doctors') {
            // Only fetch doctors data for doctors tab
            this._fetch_doctors_data();
        } else if (tab === 'list') {
            // Only fetch list data for appointments tab
            this._fetch_list_data();
        }
        
        if (tab === 'overview') {
            this._loadChartJsAndRender();
        } else {
            if (this.pieChart) { this.pieChart.destroy(); this.pieChart = null; }
            if (this.barChart) { this.barChart.destroy(); this.barChart = null; }
        }
    }

    go_to_previous_page() {
        if (this.state.current_page > 1) {
            this.state.current_page -= 1;
            this._fetch_list_data();
        }
    }

    go_to_next_page() {
        const total_pages = Math.ceil(this.state.total_records / this.state.records_per_page);
        if (this.state.current_page < total_pages) {
            this.state.current_page += 1;
            this._fetch_list_data();
        }
    }

    open_appointment_form(record) {
        this.actionManager.doAction({
            type: 'ir.actions.act_window',
            name: 'Appointment',
            res_model: 'clinic.appointment',
            res_id: record.id,
            views: [[false, 'form']],
            target: 'new',
        });
    }

    show_booked_slot_message() {
        this.actionManager.doAction({
            type: 'ir.actions.client',
            tag: 'display_notification',
            params: {
                title: 'Slot Already Booked',
                message: 'This slot is already booked. Please select another available slot.',
                type: 'warning',
                sticky: false,
            }
        });
    }

    async book_slot(doctor_id, slot_id, doctor_name, service_id) {
        // Get the selected date
        let appointment_date = this.state.selected_date;
        if (this.state.time_filter === 'today') {
            appointment_date = new Date().toISOString().split('T')[0];
        } else if (this.state.time_filter === 'tomorrow') {
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            appointment_date = tomorrow.toISOString().split('T')[0];
        }
        
        // Open appointment form with pre-filled data
        this.actionManager.doAction({
            name: 'New Appointment',
            type: 'ir.actions.act_window',
            res_model: 'clinic.appointment',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                'default_doctor_id': doctor_id,
                'default_slot_id': slot_id,
                'default_appointment_date': appointment_date,
                'default_service_id': service_id || false,
            }
        });
    }
}

AppointmentDashboard.template = "clinic_management.AppointmentDashboard";
actionRegistry.add("appointment_dashboard_tag", AppointmentDashboard);
