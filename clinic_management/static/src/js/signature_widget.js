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
        this.doctorTemplate = null; // base64 image for doctor's prescription template

        onMounted(this.onMounted.bind(this));
        onWillDestroy(() => {
            this.saveDrawing();
            if (this.saveTimeout) {
                clearTimeout(this.saveTimeout);
            }
        });
    }

    async onMounted() {
        await this.loadDoctorTemplate();
        this.renderCanvas();
    }

    renderCanvas() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext("2d");
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";

        // Always load existing prescription if available
        const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
        const existingImage = rd[this.props.name];
        if (existingImage) {
            this.loadExistingPrescription(canvas, ctx);
        } else if (this.doctorTemplate) {
            // No existing prescription but template available - initialize with template
            this.initializeWithTemplate(canvas, ctx);
        } else {
            // No template, just clear canvas
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }

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
        // Save composite image with template + drawing
        this.saveCompositeImage(canvas);
        
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
            this.saveTimeout = null;
        }
    }

    saveSimpleCanvas(canvas) {
        // Create composite image with template + drawing
        this.saveCompositeImage(canvas);
    }

    saveCompositeImage(canvas) {
        // Create composite canvas with template background + drawing
        const compositeCanvas = document.createElement('canvas');
        compositeCanvas.width = canvas.width;
        compositeCanvas.height = canvas.height;
        const ctx = compositeCanvas.getContext('2d');

        // White background first
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, compositeCanvas.width, compositeCanvas.height);

        // Draw template if available
        if (this.doctorTemplate) {
            const templateImg = new Image();
            templateImg.onload = () => {
                try {
                    // Draw template background
                    ctx.drawImage(templateImg, 0, 0, compositeCanvas.width, compositeCanvas.height);
                    
                    // Draw canvas content (drawing) on top
                    ctx.drawImage(canvas, 0, 0, compositeCanvas.width, compositeCanvas.height);
                    
                    // Save composite
                    const dataURL = compositeCanvas.toDataURL("image/png", 1.0); // Max quality
                    const base64 = dataURL.split(",")[1];
                    
                    console.log('Saving composite image with template + drawing');
                    
                    if (this.props.record && this.props.name) {
                        this.props.record.update({ [this.props.name]: base64 });
                    } else if (this.props.onChange) {
                        this.props.onChange(base64);
                    }
                } catch (error) {
                    console.error('Error creating composite image:', error);
                    // Fallback to canvas only
                    this.saveFallbackCanvas(canvas);
                }
            };
            templateImg.onerror = () => {
                console.warn('Template image failed to load, saving canvas only');
                this.saveFallbackCanvas(canvas);
            };
            templateImg.src = 'data:image/png;base64,' + this.doctorTemplate;
        } else {
            // No template, save canvas only
            this.saveFallbackCanvas(canvas);
        }
    }

    saveFallbackCanvas(canvas) {
        const dataURL = canvas.toDataURL("image/png", 1.0);
        const base64 = dataURL.split(",")[1];
        
        try {
            if (this.props.record && this.props.name) {
                this.props.record.update({ [this.props.name]: base64 });
            } else if (this.props.onChange) {
                this.props.onChange(base64);
            }
        } catch (e) {
            console.error('Error saving canvas:', e);
        }
    }


    async loadDoctorTemplate() {
        try {
            const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
            const doctorId = rd.doctor_id ? (Array.isArray(rd.doctor_id) ? rd.doctor_id[0] : rd.doctor_id) : null;
            if (!doctorId) return;

            const result = await rpc('/web/dataset/call_kw', {
                model: 'clinic.doctor',
                method: 'read',
                args: [[doctorId], ['prescription_template_image']],
                kwargs: {}
            });
            if (result && result.length > 0) {
                this.doctorTemplate = result[0].prescription_template_image || null;
            }
        } catch (e) {
            console.warn('Could not load doctor template:', e.message);
        }
    }

    initializeWithTemplate(canvas, ctx) {
        // Initialize canvas with template for first time
        if (this.doctorTemplate) {
            // Save template as initial medicine_image
            setTimeout(() => {
                this.saveCompositeImage(canvas);
            }, 100);
        }
    }

    drawDoctorTemplate(canvas, ctx) {
        // Keep canvas transparent - template is shown via CSS background
        // Template will be composite with drawing during save
        const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
        if (!rd[this.props.name] && this.doctorTemplate) {
            // If no existing drawing, save the template as initial medicine_image
            this.saveCompositeImage(canvas);
        }
    }
}

registry.category("fields").add("draw_canvas", {
    component: DrawCanvasWidget,
});