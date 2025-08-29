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

        // Initialize state
        const initialState = {
            total_appointments: 0,
            total_draft: 0,
            total_confirmed: 0,
            total_checked_in: 0,
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
            time_filter: null,
            active_tab: 'overview',
            records: [],
            current_page: 1,
            records_per_page: 15,
            total_records: 0,
            selected_state: null,
        };

        this.state = useState(initialState);

        // Fetch data on component mount
        onWillStart(async () => {
            await this._fetch_doctors();
            await this._fetch_data();
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

    async _fetch_data() {
        try {
            // Fetch dashboard tile data
            const result = await this.orm.call("clinic.appointment", "get_appointment_dashboard_data", [
                this.state.doctor_id, this.state.time_filter
            ]);
            
            Object.assign(this.state, result);

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
                this.state.records_per_page
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
            checked_in: this.state.total_checked_in,
            in_consultation: this.state.total_in_consultation,
            no_show: this.state.total_no_show,
            cancelled: this.state.total_cancelled,
            draft: this.state.total_draft
        });

        this.pieChart = new window.Chart(ctx, {
            type: 'pie',
            data: {
                labels: ['Confirmed', 'Completed', 'Checked In', 'In Consultation', 'No Show', 'Cancelled', 'Draft'],
                datasets: [{
                    data: [
                        this.state.total_confirmed,
                        this.state.total_completed,
                        this.state.total_checked_in,
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
            checked_in: this.state.total_checked_in,
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
                        this.state.total_checked_in,
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
        this.state.time_filter = this.state.time_filter === filter ? null : filter;
        this.state.current_page = 1;
        this._fetch_data();
    }

    on_doctor_change(event) {
        this.state.doctor_id = event.target.value ? parseInt(event.target.value, 10) : null;
        this.state.current_page = 1;
        this._fetch_data();
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
        this._fetch_list_data();
        
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
}

AppointmentDashboard.template = "clinic_management.AppointmentDashboard";
actionRegistry.add("appointment_dashboard_tag", AppointmentDashboard);
