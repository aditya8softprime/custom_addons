/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";


class ReceptionistDashboard extends Component {
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: [String, Number], optional: true },
        updateActionState: { type: Function, optional: true },
        className: { type: String, optional: true },
    };
    setup() {
        this.actionService = useService("action");
        this.state = useState({
            today_appointments: [],
            pending_appointments: [],
            doctor_schedules: [],
            loading: true
        });
        this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            const data = await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "get_receptionist_dashboard_data",
                args: [],
                kwargs: {},
            });

            if (data.error) {
                console.error("Backend error:", data.error);
                this.state.error = data.error;
                this.state.loading = false;
                return;
            }

            this.state.today_appointments = data.today_appointments?.data || [];
            this.state.pending_appointments = data.pending_appointments?.data || [];
            this.state.doctor_schedules = data.doctor_schedules?.data || [];
            this.state.loading = false;
            this.state.error = null;
        } catch (error) {
            console.error("Error loading receptionist dashboard:", error);
            this.state.error = error.message || "Failed to load dashboard data";
            this.state.loading = false;
        }
    }

    async openTodayAppointments() {
        try {
            await this.actionService.doAction("clinic_management.action_receptionist_today_appointments");
        } catch (error) {
            console.error("Error opening today appointments:", error);
        }
    }

    async openPendingAppointments() {
        try {
            await this.actionService.doAction("clinic_management.action_receptionist_pending_appointments");
        } catch (error) {
            console.error("Error opening pending appointments:", error);
        }
    }

    async openQuickBooking() {
        try {
            await this.actionService.doAction("clinic_management.action_quick_appointment_booking");
        } catch (error) {
            console.error("Error opening quick booking:", error);
        }
    }

    async checkInPatient(appointmentId) {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "update_appointment_status",
                args: [appointmentId, "waiting"],
                kwargs: {},
            });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error checking in patient:", error);
            this.state.error = error.message || "Failed to check in patient";
        }
    }

    async cancelAppointment(appointmentId) {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "update_appointment_status",
                args: [appointmentId, "cancelled"],
                kwargs: {},
            });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error cancelling appointment:", error);
            this.state.error = error.message || "Failed to cancel appointment";
        }
    }
}

ReceptionistDashboard.template = "clinic_management.ReceptionistDashboardTemplate";

class DoctorDashboard extends Component {
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: [String, Number], optional: true },
        updateActionState: { type: Function, optional: true },
        className: { type: String, optional: true },
    };
    setup() {
        this.actionService = useService("action");
        this.state = useState({
            doctor_info: {},
            today_patients: [],
            doctor_schedule: [],
            missed_patients: [],
            loading: true
        });
        this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            const data = await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "get_doctor_dashboard_data",
                args: [],
                kwargs: {},
            });

            if (data.error) {
                console.error("Backend error:", data.error);
                this.state.error = data.error;
                this.state.loading = false;
                return;
            }

            this.state.doctor_info = data.doctor_info || {};
            this.state.today_patients = data.today_patients?.data || [];
            this.state.doctor_schedule = data.doctor_schedule?.data || [];
            this.state.missed_patients = data.missed_patients?.data || [];
            this.state.loading = false;
            this.state.error = null;
        } catch (error) {
            console.error("Error loading doctor dashboard:", error);
            this.state.error = error.message || "Failed to load dashboard data";
            this.state.loading = false;
        }
    }

    async openTodayPatients() {
        try {
            await this.actionService.doAction("clinic_management.action_doctor_today_patients");
        } catch (error) {
            console.error("Error opening today patients:", error);
        }
    }

    async openSchedule() {
        try {
            await this.actionService.doAction("clinic_management.action_doctor_schedule");
        } catch (error) {
            console.error("Error opening schedule:", error);
        }
    }

    async openMissedPatients() {
        try {
            await this.actionService.doAction("clinic_management.action_doctor_missed_patients");
        } catch (error) {
            console.error("Error opening missed patients:", error);
        }
    }

    async startConsultation() {
        try {
            await this.actionService.doAction("clinic_management.action_start_consultation");
        } catch (error) {
            console.error("Error starting consultation:", error);
        }
    }

    async markCheckedIn(appointmentId) {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "update_appointment_status",
                args: [appointmentId, "waiting"],
                kwargs: {},
            });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error marking patient checked in:", error);
            this.state.error = error.message || "Failed to mark patient checked in";
        }
    }

    async completeConsultation(appointmentId) {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "update_appointment_status",
                args: [appointmentId, "completed"],
                kwargs: {},
            });
            await this.loadDashboardData();
        } catch (error) {
            console.error("Error completing consultation:", error);
            this.state.error = error.message || "Failed to complete consultation";
        }
    }
}

DoctorDashboard.template = "clinic_management.DoctorDashboardTemplate";

class AdminDashboard extends Component {
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: [String, Number], optional: true },
        updateActionState: { type: Function, optional: true },
        className: { type: String, optional: true },
    };
    setup() {
        this.actionService = useService("action");
        this.state = useState({
            appointments_summary: {},
            revenue_overview: {},
            doctor_utilization: [],
            upcoming_leaves: [],
            service_popularity: {},
            loading: true
        });
        this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            if (!this.rpc) {
                throw new Error("RPC service is not available");
            }
            const data = await this.rpc("/web/dataset/call_kw", {
                model: "clinic.dashboard",
                method: "get_admin_dashboard_data",
                args: [],
                kwargs: {},
            });

            if (data.error) {
                console.error("Backend error:", data.error);
                this.state.error = data.error;
                this.state.loading = false;
                return;
            }

            this.state.appointments_summary = data.appointments_summary || {};
            this.state.revenue_overview = data.revenue_overview || {};
            this.state.doctor_utilization = data.doctor_utilization || [];
            this.state.upcoming_leaves = data.upcoming_leaves?.data || [];
            this.state.service_popularity = data.service_popularity || {};
            this.state.loading = false;
            this.state.error = null;
        } catch (error) {
            console.error("Error loading admin dashboard:", error);
            this.state.error = error.message || "Failed to load dashboard data";
            this.state.loading = false;
        }
    }

    async openAppointmentsSummary() {
        try {
            await this.actionService.doAction("clinic_management.action_admin_appointments_summary");
        } catch (error) {
            console.error("Error opening appointments summary:", error);
        }
    }

    async openRevenueOverview() {
        try {
            await this.actionService.doAction("clinic_management.action_admin_revenue_overview");
        } catch (error) {
            console.error("Error opening revenue overview:", error);
        }
    }

    async openDoctorUtilization() {
        try {
            await this.actionService.doAction("clinic_management.action_admin_doctor_utilization");
        } catch (error) {
            console.error("Error opening doctor utilization:", error);
        }
    }

    async openUpcomingLeaves() {
        try {
            await this.actionService.doAction("clinic_management.action_admin_upcoming_leaves");
        } catch (error) {
            console.error("Error opening upcoming leaves:", error);
        }
    }

    async openServicePopularity() {
        try {
            await this.actionService.doAction("clinic_management.action_admin_service_popularity");
        } catch (error) {
            console.error("Error opening service popularity:", error);
        }
    }
}

AdminDashboard.template = "clinic_management.AdminDashboardTemplate";

registry.category("actions").add("receptionist_dashboard_tag", ReceptionistDashboard);
registry.category("actions").add("doctor_dashboard_tag", DoctorDashboard);
registry.category("actions").add("admin_dashboard_tag", AdminDashboard);