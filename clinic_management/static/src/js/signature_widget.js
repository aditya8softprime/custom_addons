/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, useRef } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class DrawCanvasWidget extends Component {
    static template = "clinic_management.DrawCanvasWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef = useRef("canvas");
        onMounted(this.renderCanvas.bind(this));
    }

    renderCanvas() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";

        let isDrawing = false;
        let lastX = 0;
        let lastY = 0;

        const pointerPos = (ev) => {
            const rect = canvas.getBoundingClientRect();
            // Support touch events: use first touch if present
            const clientX = (ev.touches && ev.touches[0]) ? ev.touches[0].clientX : ev.clientX;
            const clientY = (ev.touches && ev.touches[0]) ? ev.touches[0].clientY : ev.clientY;
            // When canvas display size (CSS) differs from its pixel buffer, scale coordinates
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            return {
                x: (clientX - rect.left) * scaleX,
                y: (clientY - rect.top) * scaleY,
            };
        };

        const draw = (e) => {
            if (!isDrawing) return;
            const pos = pointerPos(e);
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(pos.x, pos.y);
            ctx.stroke();
            lastX = pos.x;
            lastY = pos.y;
        };

        canvas.addEventListener("pointerdown", (e) => {
            isDrawing = true;
            const pos = pointerPos(e);
            lastX = pos.x;
            lastY = pos.y;
        });
        canvas.addEventListener("pointermove", draw);
        canvas.addEventListener("pointerup", () => {
            isDrawing = false;
            this.saveDrawing();
        });
        canvas.addEventListener("pointerout", () => {
            isDrawing = false;
        });
    }

    saveDrawing() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        // Build a composite image that includes header, the handwriting canvas and footer
        // so the stored binary matches the full template visible in the form.
        try {
            const width = canvas.width;
            const height = canvas.height;

            // Create an offscreen composite canvas
            const composite = document.createElement('canvas');
            composite.width = width;
            composite.height = height;
            const ctx = composite.getContext('2d');

            // White background
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, width, height);

            // Estimate header/footer heights as fractions of the A4 buffer
            const headerH = Math.round(height * 0.12); // ~12% for header
            const footerH = Math.round(height * 0.04); // ~4% for footer

            // Get record data for header/footer text
            const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
            const companyName = rd.company_name || 'Clinic Name';
            const companyStreet = rd.company_street || '';
            const companyCity = rd.company_city || '';
            const companyZip = rd.company_zip || '';
            const companyPhone = rd.company_phone || '';
            const patientName = (rd.patient_id && rd.patient_id[1]) ? rd.patient_id[1] : '';
            const patientAge = rd.patient_age || '';
            const prescriptionDate = rd.prescription_date || new Date().toLocaleDateString();

            // Header background gradient to match template
            const headerGrad = ctx.createLinearGradient(0, 0, width, 0);
            headerGrad.addColorStop(0, '#4e73df');
            headerGrad.addColorStop(1, '#1cc88a');
            ctx.fillStyle = headerGrad;
            ctx.fillRect(0, 0, width, headerH + 6);

            // Divider (green) under header (thin)
            ctx.fillStyle = '#1cc88a';
            ctx.fillRect(0, headerH + 6, width, 3);

            // Header text (left)
            ctx.fillStyle = '#ffffff';
            ctx.textBaseline = 'top';
            ctx.font = Math.round(headerH * 0.40) + 'px sans-serif';
            ctx.fillText(companyName, 60, 18);
            ctx.font = Math.round(headerH * 0.18) + 'px sans-serif';
            let addrY = 18 + Math.round(headerH * 0.40) + 6;
            if (companyStreet) { ctx.fillStyle = 'rgba(224,240,255,0.95)'; ctx.fillText(companyStreet, 60, addrY); addrY += Math.round(headerH * 0.18) + 4; }
            let cityLine = '';
            if (companyCity) cityLine += companyCity;
            if (companyZip) cityLine += (cityLine ? ', ' : '') + companyZip;
            if (cityLine) { ctx.fillStyle = 'rgba(224,240,255,0.95)'; ctx.fillText(cityLine, 60, addrY); addrY += Math.round(headerH * 0.18) + 4; }
            if (companyPhone) { ctx.fillStyle = 'rgba(224,240,255,0.95)'; ctx.fillText('Tel: ' + companyPhone, 60, addrY); }

            // Header right: patient info box with translucent background
            const boxW = Math.round(width * 0.34);
            const boxH = Math.round(headerH * 0.9);
            const boxX = width - boxW - 60;
            const boxY = 18;
            // rounded rect function
            function roundRect(ctx, x, y, w, h, r) {
                const radius = Math.min(r, h / 2, w / 2);
                ctx.beginPath();
                ctx.moveTo(x + radius, y);
                ctx.arcTo(x + w, y, x + w, y + h, radius);
                ctx.arcTo(x + w, y + h, x, y + h, radius);
                ctx.arcTo(x, y + h, x, y, radius);
                ctx.arcTo(x, y, x + w, y, radius);
                ctx.closePath();
            }
            ctx.fillStyle = 'rgba(255,255,255,0.15)';
            roundRect(ctx, boxX, boxY, boxW, boxH, 12);
            ctx.fill();
            // patient text inside box
            ctx.fillStyle = '#ffffff';
            ctx.textAlign = 'left';
            ctx.font = Math.round(headerH * 0.20) + 'px sans-serif';
            const px = boxX + 12;
            let py = boxY + 8;
            ctx.fillText('Patient: ' + patientName, px, py);
            py += Math.round(headerH * 0.22) + 6;
            ctx.fillText('Age: ' + patientAge + ' yrs', px, py);
            py += Math.round(headerH * 0.22) + 6;
            ctx.fillText('Date: ' + prescriptionDate, px, py);
            ctx.textAlign = 'left';

            // Draw the handwriting canvas into the composite area (scale to fit remaining space)
            // We'll scale the original canvas to occupy the area between header and footer.
            const drawingH = height - headerH - footerH - 40; // small padding
            const drawingY = headerH + 20;
            try {
                // Draw original canvas content into composite synchronously.
                // Drawing a canvas onto another canvas is synchronous and avoids load races.
                ctx.drawImage(canvas, 0, drawingY, width, drawingH);
            } catch (e) {
                // ignore and continue
            }

            // Footer gradient and text
            const footerGrad = ctx.createLinearGradient(0, height - footerH - 4, width, height - footerH - 4);
            footerGrad.addColorStop(0, '#1cc88a');
            footerGrad.addColorStop(1, '#4e73df');
            ctx.fillStyle = footerGrad;
            ctx.fillRect(0, height - footerH - 4, width, footerH + 8);
            ctx.fillStyle = '#ffffff';
            ctx.font = Math.round(footerH * 0.35) + 'px sans-serif';
            const footerY = height - footerH + Math.round(footerH * 0.15);
            const footerText = (companyName ? companyName + ' - ' : '') + (companyStreet || '');
            ctx.textAlign = 'center';
            ctx.fillText(footerText, width / 2, footerY);

            // Export composite to base64
            const dataURL = composite.toDataURL('image/png');
            const base64 = dataURL.split(',')[1];

            // Persist into record using record.update when possible
            try {
                if (this.props.record && this.props.name) {
                    this.props.record.update({ [this.props.name]: base64 });
                    return;
                }
            } catch (e) {
                // fallback
            }
            if (this.props.onChange) {
                this.props.onChange(base64);
            }
            return;
        } catch (err) {
            // Fallback to previous behaviour: save raw canvas image
        }

        // Fallback: just save the raw canvas drawing
        const dataURL = canvas.toDataURL("image/png");
        const base64 = dataURL.split(",")[1]; // strip "data:image/png;base64,"
        try {
            if (this.props.record && this.props.name) {
                this.props.record.update({ [this.props.name]: base64 });
                return;
            }
        } catch (e) {
            // ignore
        }
        if (this.props.onChange) {
            this.props.onChange(base64);
        }
    }
}

registry.category("fields").add("draw_canvas", {
    component: DrawCanvasWidget,
});
