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
    this.headerImgB64 = null; // base64 header image (doctor/company)
    this.footerImgB64 = null; // base64 footer image (doctor/company)
    this.drawingArea = null; // allowed drawing area coordinates (optional)
    this.state = useState({
            currentPage: 1,
            totalPages: 1,
            tool: 'pen',
            penSize: 2,
            eraserSize: 32,
            penColor: '#000000',
            headerB64: null,
            footerB64: null,
        });

        onMounted(this.onMounted.bind(this));
        onWillDestroy(() => {
            this.saveDrawing();
            if (this.saveTimeout) {
                clearTimeout(this.saveTimeout);
            }
        });
    }

    async onMounted() {
        await this.loadHeaderFooterImages();
        // Do not call backend analysis; use a simple default area (or none)
        this.drawingArea = { x: 0.08, y: 0.18, width: 0.84, height: 0.64 };
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
        canvas.style.touchAction = 'none';
        canvas.style.pointerEvents = 'auto';
        this.updateCursor();

        const ctx = canvas.getContext("2d");
        // Set initial drawing properties
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        this.updateDrawingSettings(ctx);

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
                    // Eraser: punch holes in current bitmap
                    ctx.globalCompositeOperation = 'destination-out';
                    ctx.strokeStyle = 'rgba(0,0,0,1)';
                    ctx.lineWidth = this.state.eraserSize;
                } else {
                    // Pen: normal drawing with color
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = this.state.penColor;
                    ctx.lineWidth = this.state.penSize;
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
                // No existing image: start with transparent canvas; header/footer shown outside
                ctx.clearRect(0, 0, canvas.width, canvas.height);
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
        // Create composite image with header/footer + drawing
        this.saveCompositeImage(canvas);
    }

    saveCompositeImage(canvas) {
        const loadImg = (b64) => new Promise((resolve, reject) => {
            if (!b64) return resolve(null);
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = reject;
            img.src = 'data:image/png;base64,' + b64;
        });

        Promise.all([loadImg(this.headerImgB64), loadImg(this.footerImgB64)])
            .then(([headerImg, footerImg]) => {
                try {
                    const headerH = headerImg ? Math.round(canvas.width * (headerImg.naturalHeight || headerImg.height) / (headerImg.naturalWidth || headerImg.width)) : 0;
                    const footerH = footerImg ? Math.round(canvas.width * (footerImg.naturalHeight || footerImg.height) / (footerImg.naturalWidth || footerImg.width)) : 0;
                    const compositeCanvas = document.createElement('canvas');
                    compositeCanvas.width = canvas.width;
                    compositeCanvas.height = headerH + canvas.height + footerH;
                    const ctx = compositeCanvas.getContext('2d');
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, compositeCanvas.width, compositeCanvas.height);
                    if (headerImg && headerH > 0) {
                        ctx.drawImage(headerImg, 0, 0, compositeCanvas.width, headerH);
                    }
                    ctx.drawImage(canvas, 0, headerH);
                    if (footerImg && footerH > 0) {
                        ctx.drawImage(footerImg, 0, headerH + canvas.height, compositeCanvas.width, footerH);
                    }
                    const dataURL = compositeCanvas.toDataURL('image/png', 1.0);
                    const base64 = dataURL.split(',')[1];
                    this._storeImageForCurrentPage(base64);
                } catch (e) {
                    console.error('Composite save failed, fallback to canvas only:', e);
                    this.saveFallbackCanvas(canvas);
                }
            })
            .catch((e) => {
                console.warn('Header/footer load failed, saving canvas only', e);
                this.saveFallbackCanvas(canvas);
            });
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
        // Composite and store now: header + canvas + footer
        try {
            const loadImg = (b64) => new Promise((resolve, reject) => {
                if (!b64) return resolve(null);
                const img = new Image();
                img.onload = () => resolve(img);
                img.onerror = reject;
                img.src = 'data:image/png;base64,' + b64;
            });
            const [headerImg, footerImg] = await Promise.all([loadImg(this.headerImgB64), loadImg(this.footerImgB64)]);
            const headerH = headerImg ? Math.round(canvas.width * (headerImg.naturalHeight || headerImg.height) / (headerImg.naturalWidth || headerImg.width)) : 0;
            const footerH = footerImg ? Math.round(canvas.width * (footerImg.naturalHeight || footerImg.height) / (footerImg.naturalWidth || footerImg.width)) : 0;
            const compositeCanvas = document.createElement('canvas');
            compositeCanvas.width = canvas.width;
            compositeCanvas.height = headerH + canvas.height + footerH;
            const ctx = compositeCanvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, compositeCanvas.width, compositeCanvas.height);
            if (headerImg && headerH > 0) {
                ctx.drawImage(headerImg, 0, 0, compositeCanvas.width, headerH);
            }
            ctx.drawImage(canvas, 0, headerH);
            if (footerImg && footerH > 0) {
                ctx.drawImage(footerImg, 0, headerH + canvas.height, compositeCanvas.width, footerH);
            }
            const dataURL = compositeCanvas.toDataURL('image/png', 1.0);
            const base64 = dataURL.split(',')[1];
            await this._storeImageForCurrentPage(base64);
        } catch (e) {
            console.error('Immediate composite failed, saving canvas only:', e);
            const dataURL = canvas.toDataURL('image/png', 1.0);
            const base64 = dataURL.split(',')[1];
            await this._storeImageForCurrentPage(base64);
        }
    }


    async loadHeaderFooterImages() {
        try {
            const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
            const doctorId = rd.doctor_id ? (Array.isArray(rd.doctor_id) ? rd.doctor_id[0] : rd.doctor_id) : null;
            const companyId = rd.company_id ? (Array.isArray(rd.company_id) ? rd.company_id[0] : rd.company_id) : null;
            
            console.log('Loading header/footer images - doctorId:', doctorId, 'companyId:', companyId);
            
            let header = null;
            let footer = null;
            
            if (doctorId) {
                console.log('Fetching from doctor:', doctorId);
                const docRes = await rpc('/web/dataset/call_kw', {
                    model: 'clinic.doctor',
                    method: 'read',
                    args: [[doctorId], ['header_image', 'footer_image']],
                    kwargs: {}
                });
                console.log('Doctor response:', docRes);
                if (docRes && docRes.length > 0) {
                    header = docRes[0].header_image || null;
                    footer = docRes[0].footer_image || null;
                    console.log('Doctor header:', !!header, 'footer:', !!footer);
                }
            }
            
            if ((!header || !footer) && companyId) {
                console.log('Fetching from company:', companyId, 'need header:', !header, 'need footer:', !footer);
                const compRes = await rpc('/web/dataset/call_kw', {
                    model: 'res.company',
                    method: 'read',
                    args: [[companyId], ['header_image', 'footer_image']],
                    kwargs: {}
                });
                console.log('Company response:', compRes);
                if (compRes && compRes.length > 0) {
                    header = header || compRes[0].header_image || null;
                    footer = footer || compRes[0].footer_image || null;
                    console.log('Final header:', !!header, 'footer:', !!footer);
                }
            }
            
            this.headerImgB64 = header;
            this.footerImgB64 = footer;
            // Update reactive state so template <img> tags can render base64 directly
            this.state.headerB64 = header;
            this.state.footerB64 = footer;
            
            console.log('State updated - headerB64:', !!this.state.headerB64, 'footerB64:', !!this.state.footerB64);
        } catch (e) {
            console.error('Could not load header/footer images:', e);
        }
    }

    async loadDrawingArea() {
        // Analysis removed: use a simple default drawing area (optional)
        this.drawingArea = { x: 0.08, y: 0.18, width: 0.84, height: 0.64 };
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

    // Update drawing settings based on current tool
    updateDrawingSettings(ctx) {
        if (this.state.tool === 'eraser') {
            ctx.lineWidth = this.state.eraserSize;
            ctx.strokeStyle = 'rgba(0,0,0,1)';
        } else {
            ctx.lineWidth = this.state.penSize;
            ctx.strokeStyle = this.state.penColor;
        }
    }

    // Update cursor based on tool and size
    updateCursor() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        
        if (this.state.tool === 'eraser') {
            // Create eraser cursor - circle showing eraser size
            const size = Math.min(this.state.eraserSize, 50); // Cap display size at 50px for visibility
            const cursorSvg = `
                <svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="${size/2}" cy="${size/2}" r="${size/2-1}" 
                            fill="none" stroke="#ff6b6b" stroke-width="2" opacity="0.8"/>
                </svg>
            `;
            const encodedSvg = encodeURIComponent(cursorSvg);
            canvas.style.cursor = `url("data:image/svg+xml,${encodedSvg}") ${size/2} ${size/2}, auto`;
        } else {
            // Pen cursor - crosshair with dot showing pen size
            const size = Math.min(this.state.penSize * 3, 20); // Scale up for visibility
            const cursorSvg = `
                <svg width="${size + 10}" height="${size + 10}" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="${(size + 10)/2}" cy="${(size + 10)/2}" r="${size/2}" 
                            fill="${this.state.penColor}" opacity="0.7"/>
                    <circle cx="${(size + 10)/2}" cy="${(size + 10)/2}" r="${size/2}" 
                            fill="none" stroke="#333" stroke-width="1"/>
                </svg>
            `;
            const encodedSvg = encodeURIComponent(cursorSvg);
            canvas.style.cursor = `url("data:image/svg+xml,${encodedSvg}") ${(size + 10)/2} ${(size + 10)/2}, crosshair`;
        }
    }

    // Toolbar handlers
    onToolPen() {
        this.state.tool = 'pen';
        this.updateCursor();
    }
    
    onToolEraser() {
        this.state.tool = 'eraser';
        this.updateCursor();
    }
    
    onPenSizeChange(ev) {
        const v = parseInt(ev.target.value, 10);
        this.state.penSize = isNaN(v) ? 2 : v;
        this.updateCursor();
    }
    
    onEraserSizeChange(ev) {
        const v = parseInt(ev.target.value, 10);
        this.state.eraserSize = isNaN(v) ? 32 : v;
        this.updateCursor();
    }
    
    onColorChange(ev) {
        this.state.penColor = ev.target.value || '#000000';
        this.updateCursor();
    }
}

registry.category("fields").add("draw_canvas", {
    component: DrawCanvasWidget,
});