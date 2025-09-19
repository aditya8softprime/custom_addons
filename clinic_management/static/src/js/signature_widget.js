/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillDestroy, useRef } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { rpc } from "@web/core/network/rpc";

class DrawCanvasWidget extends Component {
    static template = "clinic_management.DrawCanvasWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef = useRef("canvas");
        this.saveTimeout = null;
        this.isDrawing = false;
        
        onMounted(this.renderCanvas.bind(this));
        onWillDestroy(() => {
            this.saveDrawing();
            if (this.saveTimeout) {
                clearTimeout(this.saveTimeout);
            }
        });
    }

    renderCanvas() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";

        // Load existing prescription if available
        this.loadExistingPrescription(canvas, ctx);

        let lastX = 0;
        let lastY = 0;

        const pointerPos = (ev) => {
            const rect = canvas.getBoundingClientRect();
            const clientX = (ev.touches && ev.touches[0]) ? ev.touches[0].clientX : ev.clientX;
            const clientY = (ev.touches && ev.touches[0]) ? ev.touches[0].clientY : ev.clientY;
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            return {
                x: (clientX - rect.left) * scaleX,
                y: (clientY - rect.top) * scaleY,
            };
        };

        const draw = (e) => {
            if (!this.isDrawing) return;
            const pos = pointerPos(e);
            ctx.beginPath();
            ctx.moveTo(lastX, lastY);
            ctx.lineTo(pos.x, pos.y);
            ctx.stroke();
            lastX = pos.x;
            lastY = pos.y;
        };

        canvas.addEventListener("pointerdown", (e) => {
            this.isDrawing = true;
            const pos = pointerPos(e);
            lastX = pos.x;
            lastY = pos.y;
        });
        
        canvas.addEventListener("pointermove", draw);
        
        canvas.addEventListener("pointerup", () => {
            this.isDrawing = false;
            this.debouncedSave();
        });
        
        canvas.addEventListener("pointerout", () => {
            this.isDrawing = false;
            this.debouncedSave();
        });
    }

    loadExistingPrescription(canvas, ctx) {
        const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
        const existingImage = rd[this.props.name];
        
        if (existingImage) {
            const img = new Image();
            img.onload = () => {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            };
            img.src = 'data:image/png;base64,' + existingImage;
        }
    }

    debouncedSave() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        
        this.saveTimeout = setTimeout(() => {
            this.saveDrawing();
        }, 500);
    }

    async saveDrawing() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        
        try {
            // Try to get company images
            const companyData = await this.fetchCompanyData();
            this.createCompositeImage(canvas, companyData);
        } catch (e) {
            // Fallback: just save the raw canvas drawing
            this.saveSimpleCanvas(canvas);
        }
        
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
            this.saveTimeout = null;
        }
    }

    async fetchCompanyData() {
        const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
        const companyId = rd.company_id ? (Array.isArray(rd.company_id) ? rd.company_id[0] : rd.company_id) : null;
        
        if (!companyId) {
            throw new Error('No company_id found');
        }

        // Fetch company data
        const result = await rpc('/web/dataset/call_kw', {
            model: 'res.company',
            method: 'read',
            args: [[companyId], ['header_image', 'footer_image']],
            kwargs: {}
        });

        if (result && result.length > 0) {
            return {
                company_header_image: result[0].header_image,
                company_footer_image: result[0].footer_image
            };
        }
        
        throw new Error('Company not found');
    }

    saveSimpleCanvas(canvas) {
        const dataURL = canvas.toDataURL("image/png");
        const base64 = dataURL.split(",")[1];
        
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

    createCompositeImage(canvas, companyData) {
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

        // Calculate proportional heights
        const headerH = Math.round(height * 0.12);
        const footerH = Math.round(height * 0.06);
        const drawingH = height - headerH - footerH;
        const drawingY = headerH;

        let operationsCompleted = 0;
        const totalOperations = 2; // header + footer

        const checkComplete = () => {
            operationsCompleted++;
            if (operationsCompleted >= totalOperations) {
                // Draw the canvas content
                ctx.drawImage(canvas, 0, 0, canvas.width, canvas.height, 0, drawingY, width, drawingH);
                
                // Save the composite
                this.saveComposite(composite);
            }
        };

        // Render header image or fallback
        if (companyData.company_header_image) {
            const headerImg = new Image();
            headerImg.onload = () => {
                ctx.drawImage(headerImg, 0, 0, width, headerH);
                checkComplete();
            };
            headerImg.onerror = () => {
                // Fallback gradient
                const headerGrad = ctx.createLinearGradient(0, 0, width, 0);
                headerGrad.addColorStop(0, '#4e73df');
                headerGrad.addColorStop(1, '#1cc88a');
                ctx.fillStyle = headerGrad;
                ctx.fillRect(0, 0, width, headerH);
                checkComplete();
            };
            headerImg.src = 'data:image/png;base64,' + companyData.company_header_image;
        } else {
            // Fallback gradient
            const headerGrad = ctx.createLinearGradient(0, 0, width, 0);
            headerGrad.addColorStop(0, '#4e73df');
            headerGrad.addColorStop(1, '#1cc88a');
            ctx.fillStyle = headerGrad;
            ctx.fillRect(0, 0, width, headerH);
            checkComplete();
        }

        // Render footer image or fallback
        if (companyData.company_footer_image) {
            const footerImg = new Image();
            footerImg.onload = () => {
                ctx.drawImage(footerImg, 0, height - footerH, width, footerH);
                checkComplete();
            };
            footerImg.onerror = () => {
                // Fallback gradient
                const footerGrad = ctx.createLinearGradient(0, height - footerH, width, height - footerH);
                footerGrad.addColorStop(0, '#1cc88a');
                footerGrad.addColorStop(1, '#4e73df');
                ctx.fillStyle = footerGrad;
                ctx.fillRect(0, height - footerH, width, footerH);
                checkComplete();
            };
            footerImg.src = 'data:image/png;base64,' + companyData.company_footer_image;
        } else {
            // Fallback gradient
            const footerGrad = ctx.createLinearGradient(0, height - footerH, width, height - footerH);
            footerGrad.addColorStop(0, '#1cc88a');
            footerGrad.addColorStop(1, '#4e73df');
            ctx.fillStyle = footerGrad;
            ctx.fillRect(0, height - footerH, width, footerH);
            checkComplete();
        }
    }

    saveComposite(composite) {
        const dataURL = composite.toDataURL('image/png');
        const base64 = dataURL.split(',')[1];

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