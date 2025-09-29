/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillDestroy, useRef, useState } from "@odoo/owl";
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
        this.drawingArea = null; // allowed drawing area coordinates
    this.state = useState({ currentPage: 1, totalPages: 1, tool: 'pen', brushSize: 2 });

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
        await this.loadDrawingArea();
        await this.initPagesState();
        this.renderCanvas();
        await this.fetchAndDrawCurrentPage();
    }

    getAppointmentId() {
        const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
        return rd.id || (this.props.record ? this.props.record.resId : null);
    }

    async initPagesState() {
        try {
            const apptId = this.getAppointmentId();
            if (!apptId) return;
            const result = await rpc('/web/dataset/call_kw', {
                model: 'clinic.appointment',
                method: 'get_prescription_pages_count',
                args: [[apptId]],
                kwargs: {}
            });
            if (result && typeof result === 'number') {
                this.state.totalPages = result;
                this.state.currentPage = Math.min(this.state.currentPage, result) || 1;
            }
        } catch (e) {
            console.warn('Could not fetch pages count:', e.message);
        }
    }

    renderCanvas() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;

        // Ensure canvas is interactive
        canvas.style.cursor = 'crosshair';
        canvas.style.touchAction = 'none';
        canvas.style.pointerEvents = 'auto';

        const ctx = canvas.getContext("2d");
    ctx.lineWidth = this.state.brushSize || 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.strokeStyle = "#000000"; // Set default drawing color

    // Start with a transparent canvas; background template is shown via CSS.
    ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Always show drawing area outline for guidance
        setTimeout(() => this.showDrawingAreaOutline(canvas, ctx), 500);

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

        let hasDrawn = false; // Track if actual drawing happened

        // const isInDrawingArea = (x, y) => {
        // const areaX = this.drawingArea.x * canvas.width;
        // const areaY = this.drawingArea.y * canvas.height;
        // const areaWidth = this.drawingArea.width * canvas.width;
        // const areaHeight = this.drawingArea.height * canvas.height;

        // return x >= areaX && x <= areaX + areaWidth && 
        //     y >= areaY && y <= areaY + areaHeight;
        // };
        const isInDrawingArea = (x, y) => {
        // Always allow drawing anywhere
        return true;
};




        const draw = (e) => {
            if (!this.isDrawing) return;
            const pos = pointerPos(e);
            
            // Check if position is within allowed drawing area
            if (!isInDrawingArea(pos.x, pos.y)) {
                // If outside drawing area, stop drawing
                this.isDrawing = false;
                return;
            }
            
            // Check if there's actual movement for drawing
            const distance = Math.sqrt(Math.pow(pos.x - lastX, 2) + Math.pow(pos.y - lastY, 2));
            if (distance > 2) { // Only draw if movement is significant (more than 2 pixels)
                ctx.save();
                if (this.state.tool === 'eraser') {
                    // Eraser: punch holes in current bitmap (keep template intact, since it's background)
                    ctx.globalCompositeOperation = 'destination-out';
                    ctx.strokeStyle = 'rgba(0,0,0,1)';
                    ctx.lineWidth = this.state.brushSize || 16;
                } else {
                    // Pen: normal drawing
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = '#000000';
                    ctx.lineWidth = this.state.brushSize || 2;
                }
                ctx.beginPath();
                ctx.moveTo(lastX, lastY);
                ctx.lineTo(pos.x, pos.y);
                ctx.stroke();
                ctx.restore();
                hasDrawn = true; // Mark that actual drawing occurred
            }
            
            lastX = pos.x;
            lastY = pos.y;
        };

        const startDrawing = (e) => {
            e.preventDefault();
            const pos = pointerPos(e);
            
            // Only start drawing if within allowed area
            if (isInDrawingArea(pos.x, pos.y)) {
                this.isDrawing = true;
                hasDrawn = false; // Reset drawing flag
                lastX = pos.x;
                lastY = pos.y;
                canvas.style.cursor = 'crosshair';
            } else {
                // Show visual feedback for restricted area
                this.showRestrictedAreaWarning();
            }
        };
        
        const stopDrawing = () => {
            if (this.isDrawing && hasDrawn) {
                // Only save if actual drawing happened
                this.debouncedSave();
            }
            this.isDrawing = false;
            hasDrawn = false;
            canvas.style.cursor = 'crosshair';
        };

        // Mouse events
        canvas.addEventListener("mousedown", startDrawing);
        canvas.addEventListener("mousemove", draw);
        canvas.addEventListener("mouseup", stopDrawing);
        canvas.addEventListener("mouseout", stopDrawing);
        
        // Touch events
        canvas.addEventListener("touchstart", (e) => {
            e.preventDefault(); // Prevent scrolling
            startDrawing(e);
        });
        canvas.addEventListener("touchmove", (e) => {
            e.preventDefault(); // Prevent scrolling
            draw(e);
        });
        canvas.addEventListener("touchend", (e) => {
            e.preventDefault();
            stopDrawing();
        });
        
        // Pointer events (fallback for modern browsers)
        canvas.addEventListener("pointerdown", startDrawing);
        canvas.addEventListener("pointermove", draw);
        canvas.addEventListener("pointerup", stopDrawing);
        canvas.addEventListener("pointerout", stopDrawing);
    }

    async fetchAndDrawCurrentPage() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const page = this.state.currentPage || 1;
        try {
            let imgB64 = null;
            const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
            if (page === 1) {
                imgB64 = rd[this.props.name] || null;
            }
            if (!imgB64) {
                const apptId = this.getAppointmentId();
                if (apptId) {
                    const result = await rpc('/web/dataset/call_kw', {
                        model: 'clinic.appointment',
                        method: 'get_prescription_page',
                        args: [[apptId], page],
                        kwargs: {}
                    });
                    imgB64 = result || null;
                }
            }
            // Draw
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (imgB64) {
                const img = new Image();
                await new Promise((resolve, reject) => {
                    img.onload = resolve;
                    img.onerror = reject;
                    img.src = 'data:image/png;base64,' + imgB64;
                });
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            } else {
                // No existing image: draw the doctor's template onto canvas so it's visible
                if (this.doctorTemplate) {
                    const templateImg = new Image();
                    await new Promise((resolve, reject) => {
                        templateImg.onload = resolve;
                        templateImg.onerror = reject;
                        templateImg.src = 'data:image/png;base64,' + this.doctorTemplate;
                    });
                    ctx.drawImage(templateImg, 0, 0, canvas.width, canvas.height);
                }
                // Also draw outline for the drawing area
                this.initializeWithTemplate(canvas, ctx);
            }
            // show drawing area outline again
            setTimeout(() => this.showDrawingAreaOutline(canvas, ctx), 300);
        } catch (e) {
            console.warn('Failed to draw page', page, e);
        }
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
        console.log('Starting composite image save...');
        
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
                    
                    console.log('Saving composite image with template + drawing, size:', base64.length);
                    
                    this._storeImageForCurrentPage(base64);
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
            console.log('No template available, saving canvas only');
            // No template, save canvas only
            this.saveFallbackCanvas(canvas);
        }
    }

    saveFallbackCanvas(canvas) {
        const dataURL = canvas.toDataURL("image/png", 1.0);
        const base64 = dataURL.split(",")[1];
        
        try {
            this._storeImageForCurrentPage(base64);
        } catch (e) {
            console.error('Error saving canvas:', e);
        }
    }

    async _storeImageForCurrentPage(base64) {
        try {
            const page = this.state.currentPage || 1;
            if (page === 1) {
                if (this.props.record && this.props.name) {
                    this.props.record.update({ [this.props.name]: base64 });
                } else if (this.props.onChange) {
                    this.props.onChange(base64);
                }
            } else {
                const apptId = this.getAppointmentId();
                if (!apptId) return;
                await rpc('/web/dataset/call_kw', {
                    model: 'clinic.appointment',
                    method: 'set_prescription_page',
                    args: [[apptId], page, base64, null],
                    kwargs: {}
                });
            }
        } catch (e) {
            console.error('Failed storing page image:', e);
        }
    }

    async onPrevPage() {
        if (this.state.currentPage <= 1) return;
        await this.saveImmediately();
        this.state.currentPage -= 1;
        await this.fetchAndDrawCurrentPage();
    }

    async onNextPage() {
        if (this.state.currentPage >= this.state.totalPages) return;
        await this.saveImmediately();
        this.state.currentPage += 1;
        await this.fetchAndDrawCurrentPage();
    }

    async onAddPage() {
        try {
            await this.saveImmediately();
            const apptId = this.getAppointmentId();
            if (!apptId) return;
            const newCount = await rpc('/web/dataset/call_kw', {
                model: 'clinic.appointment',
                method: 'add_prescription_page',
                args: [[apptId]],
                kwargs: {}
            });
            if (newCount) {
                this.state.totalPages = newCount;
                this.state.currentPage = newCount;
                // New page starts empty: fetch and draw current page (will render template to canvas)
                await this.fetchAndDrawCurrentPage();
            }
        } catch (e) {
            console.error('Failed to add page:', e);
        }
    }

    async onRemovePage() {
        try {
            const page = this.state.currentPage;
            if (this.state.totalPages <= 1) return; // must keep at least one page
            const apptId = this.getAppointmentId();
            if (!apptId) return;
            const newCount = await rpc('/web/dataset/call_kw', {
                model: 'clinic.appointment',
                method: 'remove_prescription_page',
                args: [[apptId], page],
                kwargs: {}
            });
            if (typeof newCount === 'number') {
                this.state.totalPages = newCount;
                if (this.state.currentPage > newCount) {
                    this.state.currentPage = newCount;
                }
                await this.fetchAndDrawCurrentPage();
            }
        } catch (e) {
            console.error('Failed to remove page:', e);
        }
    }

    async saveImmediately() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        // Composite and store now
        // Duplicate logic of saveCompositeImage but ensure immediate storage
        const compositeCanvas = document.createElement('canvas');
        compositeCanvas.width = canvas.width;
        compositeCanvas.height = canvas.height;
        const ctx = compositeCanvas.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, compositeCanvas.width, compositeCanvas.height);
        try {
            if (this.doctorTemplate) {
                const templateImg = new Image();
                await new Promise((resolve, reject) => {
                    templateImg.onload = resolve;
                    templateImg.onerror = reject;
                    templateImg.src = 'data:image/png;base64,' + this.doctorTemplate;
                });
                ctx.drawImage(templateImg, 0, 0, compositeCanvas.width, compositeCanvas.height);
            }
            ctx.drawImage(canvas, 0, 0, compositeCanvas.width, compositeCanvas.height);
            const dataURL = compositeCanvas.toDataURL('image/png', 1.0);
            const base64 = dataURL.split(',')[1];
            await this._storeImageForCurrentPage(base64);
        } catch (e) {
            console.error('Immediate save failed, falling back:', e);
            const dataURL = canvas.toDataURL('image/png', 1.0);
            const base64 = dataURL.split(',')[1];
            await this._storeImageForCurrentPage(base64);
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

    async loadDrawingArea() {
        try {
            const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
            const doctorId = rd.doctor_id ? (Array.isArray(rd.doctor_id) ? rd.doctor_id[0] : rd.doctor_id) : null;
            if (!doctorId) return;

            const result = await rpc('/web/dataset/call_kw', {
                model: 'clinic.doctor',
                method: 'get_drawing_area_coords',
                args: [doctorId],
                kwargs: {}
            });
            
            if (result) {
                this.drawingArea = result;
                console.log('Drawing area loaded:', this.drawingArea);
            } else {
                // Default drawing area
                this.drawingArea = {x: 0.1, y: 0.15, width: 0.8, height: 0.7};
            }
        } catch (e) {
            console.warn('Could not load drawing area:', e.message);
            // Default drawing area
            this.drawingArea = {x: 0.1, y: 0.15, width: 0.8, height: 0.7};
        }
    }

    initializeWithTemplate(canvas, ctx) {
        // Initialize canvas with template for first time
        // Template is shown via CSS background, no need to save immediately
        // Save will only happen when user actually draws something
        console.log('Template loaded as background, waiting for user drawing...');
        
        // Optionally show drawing area outline
        this.showDrawingAreaOutline(canvas, ctx);
    }

    showDrawingAreaOutline(canvas, ctx) {
        if (!this.drawingArea) return;
        
        // Draw a subtle outline of the allowed drawing area
        const areaX = this.drawingArea.x * canvas.width;
        const areaY = this.drawingArea.y * canvas.height;
        const areaWidth = this.drawingArea.width * canvas.width;
        const areaHeight = this.drawingArea.height * canvas.height;
        
        ctx.save();
        ctx.strokeStyle = 'rgba(0, 123, 255, 0.3)'; // Light blue outline
        ctx.lineWidth = 2;
        ctx.setLineDash([10, 5]); // Dashed line
        ctx.strokeRect(areaX, areaY, areaWidth, areaHeight);
        ctx.restore();
        
        // Auto-hide outline after 3 seconds
        setTimeout(() => {
            ctx.clearRect(areaX - 2, areaY - 2, areaWidth + 4, areaHeight + 4);
        }, 3000);
    }

    showRestrictedAreaWarning() {
        // Show temporary visual feedback
        console.warn('Drawing not allowed in this area. Please draw only in the designated area.');
        
        // Add visual feedback with red cursor
        const canvas = this.canvasRef.el;
        if (canvas) {
            canvas.style.cursor = 'not-allowed';
            setTimeout(() => {
                canvas.style.cursor = 'crosshair';
            }, 1000);
        }
        
        // TODO: Add toast notification for better UX
        // this.env.services.notification.add('Please draw only in the designated area', {type: 'warning'});
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

    // Toolbar handlers
    onToolPen() {
        this.state.tool = 'pen';
    }
    onToolEraser() {
        this.state.tool = 'eraser';
    }
    onBrushSizeChange(ev) {
        const v = parseInt(ev.target.value, 10);
        this.state.brushSize = isNaN(v) ? 2 : v;
    }
}

registry.category("fields").add("draw_canvas", {
    component: DrawCanvasWidget,
});