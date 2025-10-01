/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillDestroy, useRef, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { rpc } from "@web/core/network/rpc";

class DrawCanvasWidget extends Component {
    static template = "clinic_management.DrawCanvasWidget";
    static props = { ...standardFieldProps };
    
    // Static cache for header/footer images to prevent reload on tab switch
    static imageCache = new Map();
    static imageCacheTTL = 5 * 60 * 1000; // 5 minutes

    setup() {
        this.canvasRef = useRef("canvas");
        this.saveTimeout = null;
        this.isDrawing = false;
        this.headerImgB64 = null; // base64 header image (doctor/company)
        this.footerImgB64 = null; // base64 footer image (doctor/company)
        
        // Strokes-based drawing system
        this.strokes = []; // Array of stroke objects for current page
        this.currentStroke = null; // Current stroke being drawn
        this.allPageStrokes = new Map(); // Map of page number to strokes array
        
        this.state = useState({
            tool: 'pen',
            penSize: 2,
            eraserSize: 32,
            penColor: '#000000',
            headerB64: null,
            footerB64: null,
            currentPage: 1,
            totalPages: 1,
        });

        onMounted(this.onMounted.bind(this));
        onWillDestroy(() => {
            this.saveCurrentPageStrokes();
            if (this.saveTimeout) {
                clearTimeout(this.saveTimeout);
            }
        });
    }

    async onMounted() {
        await this.loadHeaderFooterImages();
        await this.initPagesState();
        this.renderCanvas();
        await this.loadAllPagesStrokes();
        this.redrawCanvas();
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

    // Load strokes for all pages
    async loadAllPagesStrokes() {
        try {
            const apptId = this.getAppointmentId();
            if (!apptId) return;
            
            // Load strokes for all pages
            for (let pageNum = 1; pageNum <= this.state.totalPages; pageNum++) {
                await this.loadStrokesForPage(pageNum);
            }
            
            // Set current page strokes
            this.strokes = this.allPageStrokes.get(this.state.currentPage) || [];
            
        } catch (e) {
            console.warn('Could not load all pages strokes:', e.message);
            this.strokes = [];
        }
    }

    async loadStrokesForPage(pageNum) {
        try {
            if (pageNum === 1) {
                // Page 1: Load from prescription_strokes field
                const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
                const strokesData = rd.prescription_strokes || '';
                
                if (strokesData) {
                    this.allPageStrokes.set(1, JSON.parse(strokesData));
                } else {
                    this.allPageStrokes.set(1, []);
                }
            } else {
                // Other pages: Load via RPC
                const apptId = this.getAppointmentId();
                if (!apptId) return;
                
                const result = await rpc('/web/dataset/call_kw', {
                    model: 'clinic.appointment',
                    method: 'get_prescription_page_strokes',
                    args: [[apptId], pageNum],
                    kwargs: {}
                });
                
                if (result) {
                    this.allPageStrokes.set(pageNum, JSON.parse(result));
                } else {
                    this.allPageStrokes.set(pageNum, []);
                }
            }
        } catch (e) {
            console.warn(`Could not load strokes for page ${pageNum}:`, e.message);
            this.allPageStrokes.set(pageNum, []);
        }
    }

    // Save strokes for current page
    async saveCurrentPageStrokes() {
        try {
            const currentPage = this.state.currentPage;
            const strokesData = JSON.stringify(this.strokes);
            
            // Update in-memory cache
            this.allPageStrokes.set(currentPage, [...this.strokes]);
            
            if (currentPage === 1) {
                // Page 1: Save to prescription_strokes field
                if (this.props.record && this.props.record.data) {
                    this.props.record.update({ prescription_strokes: strokesData });
                } else if (this.props.onChange) {
                    const currentData = this.props.record?.data || {};
                    this.props.onChange({ ...currentData, prescription_strokes: strokesData });
                }
            } else {
                // Other pages: Save via RPC
                const apptId = this.getAppointmentId();
                if (!apptId) return;
                
                await rpc('/web/dataset/call_kw', {
                    model: 'clinic.appointment',
                    method: 'set_prescription_page_strokes',
                    args: [[apptId], currentPage, strokesData],
                    kwargs: {}
                });
            }
        } catch (e) {
            console.error('Failed to save strokes for current page:', e);
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
            if (!this.isDrawing || !this.currentStroke) return;
            const pos = pointerPos(e);
            
            // Check if there's actual movement for drawing
            const distance = Math.sqrt(Math.pow(pos.x - lastX, 2) + Math.pow(pos.y - lastY, 2));
            if (distance > 2) { // Only draw if movement is significant (more than 2 pixels)
                // Add point to current stroke
                this.currentStroke.points.push({ x: pos.x, y: pos.y });
                
                // Draw the line segment on canvas
                ctx.save();
                if (this.state.tool === 'eraser') {
                    // For eraser, we'll handle it differently - remove intersecting strokes
                    this.eraseAtPoint(pos.x, pos.y);
                } else {
                    // Pen: draw line segment
                    ctx.globalCompositeOperation = 'source-over';
                    ctx.strokeStyle = this.currentStroke.color;
                    ctx.lineWidth = this.currentStroke.size;
                    ctx.lineJoin = "round";
                    ctx.lineCap = "round";
                    ctx.beginPath();
                    ctx.moveTo(lastX, lastY);
                    ctx.lineTo(pos.x, pos.y);
                    ctx.stroke();
                }
                ctx.restore();
            }
            
            lastX = pos.x;
            lastY = pos.y;
        };

        const startDrawing = (e) => {
            e.preventDefault();
            const pos = pointerPos(e);
            
            this.isDrawing = true;
            lastX = pos.x;
            lastY = pos.y;
            
            if (this.state.tool === 'eraser') {
                // Start erasing at this point
                this.eraseAtPoint(pos.x, pos.y);
            } else {
                // Create new stroke
                this.currentStroke = {
                    type: 'pen',
                    color: this.state.penColor,
                    size: this.state.penSize,
                    points: [{ x: pos.x, y: pos.y }]
                };
            }
        };
        
        const stopDrawing = () => {
            if (this.isDrawing) {
                if (this.state.tool === 'pen' && this.currentStroke && this.currentStroke.points.length > 1) {
                    // Add completed stroke to strokes array
                    this.strokes.push(this.currentStroke);
                }
                this.currentStroke = null;
                this.debouncedSave();
            }
            this.isDrawing = false;
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

    // Redraw canvas from strokes array
    redrawCanvas() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        
        // Clear canvas - header/footer are separate overlays
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Redraw all strokes
        ctx.save();
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        
        for (const stroke of this.strokes) {
            if (stroke.points && stroke.points.length > 1) {
                ctx.strokeStyle = stroke.color || '#000000';
                ctx.lineWidth = stroke.size || 2;
                ctx.globalCompositeOperation = 'source-over';
                
                ctx.beginPath();
                ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
                
                for (let i = 1; i < stroke.points.length; i++) {
                    ctx.lineTo(stroke.points[i].x, stroke.points[i].y);
                }
                
                ctx.stroke();
            }
        }
        ctx.restore();
    }



    // Eraser functionality - remove strokes that intersect with eraser circle
    eraseAtPoint(x, y) {
        const eraserRadius = this.state.eraserSize / 2;
        let modified = false;
        
        // Check each stroke for intersection with eraser circle
        for (let i = this.strokes.length - 1; i >= 0; i--) {
            const stroke = this.strokes[i];
            let shouldRemove = false;
            
            // Check if any point in the stroke is within eraser radius
            for (const point of stroke.points) {
                const distance = Math.sqrt(Math.pow(point.x - x, 2) + Math.pow(point.y - y, 2));
                if (distance <= eraserRadius) {
                    shouldRemove = true;
                    break;
                }
            }
            
            if (shouldRemove) {
                this.strokes.splice(i, 1);
                modified = true;
            }
        }
        
        // Redraw canvas if strokes were modified
        if (modified) {
            this.redrawCanvas();
        }
    }

    debouncedSave() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        
        this.saveTimeout = setTimeout(() => {
            this.saveCurrentPageStrokes();
        }, 500);
    }

    // Page navigation methods
    async onPrevPage() {
        if (this.state.currentPage <= 1) return;
        
        // Save current page before switching
        await this.saveCurrentPageStrokes();
        
        // Switch to previous page
        this.state.currentPage -= 1;
        this.strokes = this.allPageStrokes.get(this.state.currentPage) || [];
        this.redrawCanvas();
    }

    async onNextPage() {
        if (this.state.currentPage >= this.state.totalPages) return;
        
        // Save current page before switching
        await this.saveCurrentPageStrokes();
        
        // Switch to next page
        this.state.currentPage += 1;
        this.strokes = this.allPageStrokes.get(this.state.currentPage) || [];
        this.redrawCanvas();
    }

    async onAddPage() {
        try {
            // Save current page before adding new page
            await this.saveCurrentPageStrokes();
            
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
                
                // Initialize empty strokes for new page
                this.strokes = [];
                this.allPageStrokes.set(newCount, []);
                this.redrawCanvas();
            }
        } catch (e) {
            console.error('Failed to add page:', e);
        }
    }

    async onRemovePage() {
        try {
            const currentPage = this.state.currentPage;
            if (this.state.totalPages <= 1) return; // Must keep at least one page
            
            const apptId = this.getAppointmentId();
            if (!apptId) return;
            
            const newCount = await rpc('/web/dataset/call_kw', {
                model: 'clinic.appointment',
                method: 'remove_prescription_page',
                args: [[apptId], currentPage],
                kwargs: {}
            });
            
            if (typeof newCount === 'number') {
                this.state.totalPages = newCount;
                
                // Remove from memory cache
                this.allPageStrokes.delete(currentPage);
                
                // Adjust current page if needed
                if (this.state.currentPage > newCount) {
                    this.state.currentPage = newCount;
                }
                
                // Load current page strokes
                this.strokes = this.allPageStrokes.get(this.state.currentPage) || [];
                this.redrawCanvas();
            }
        } catch (e) {
            console.error('Failed to remove page:', e);
        }
    }

    // Clear current page strokes
    clearDrawing() {
        this.strokes = [];
        this.allPageStrokes.set(this.state.currentPage, []);
        this.redrawCanvas();
        this.saveCurrentPageStrokes();
    }


    async loadHeaderFooterImages() {
        try {
            const rd = (this.props.record && this.props.record.data) ? this.props.record.data : {};
            const doctorId = rd.doctor_id ? (Array.isArray(rd.doctor_id) ? rd.doctor_id[0] : rd.doctor_id) : null;
            const companyId = rd.company_id ? (Array.isArray(rd.company_id) ? rd.company_id[0] : rd.company_id) : null;
            
            // Create cache key based on doctor and company IDs
            const cacheKey = `${doctorId || 'null'}_${companyId || 'null'}`;

            const now = Date.now();

            // 1) Check in-memory cache first
            const cachedMem = DrawCanvasWidget.imageCache.get(cacheKey);
            if (cachedMem && (now - cachedMem.ts) < DrawCanvasWidget.imageCacheTTL) {
                this.headerImgB64 = cachedMem.header;
                this.footerImgB64 = cachedMem.footer;
                this.state.headerB64 = cachedMem.header;
                this.state.footerB64 = cachedMem.footer;
                return;
            }

            // 2) Check persistent cache (localStorage) to survive dev asset reloads
            let cachedLS = null;
            try {
                const lsKey = `cm_sig_header_footer_${cacheKey}`;
                const raw = window.localStorage ? window.localStorage.getItem(lsKey) : null;
                if (raw) {
                    const obj = JSON.parse(raw);
                    if (obj && obj.ts && (now - obj.ts) < DrawCanvasWidget.imageCacheTTL) {
                        cachedLS = obj;
                    }
                }
            } catch (e) {
                // localStorage may be unavailable or quota exceeded; ignore and proceed
            }

            if (cachedLS) {
                this.headerImgB64 = cachedLS.header || null;
                this.footerImgB64 = cachedLS.footer || null;
                this.state.headerB64 = this.headerImgB64;
                this.state.footerB64 = this.footerImgB64;
                // hydrate in-memory cache for faster next time
                DrawCanvasWidget.imageCache.set(cacheKey, { header: this.headerImgB64, footer: this.footerImgB64, ts: cachedLS.ts });
                return;
            }
            
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
            
            // Cache the images for future use with timestamp
            const ts = Date.now();
            DrawCanvasWidget.imageCache.set(cacheKey, { header, footer, ts });
            try {
                const lsKey = `cm_sig_header_footer_${cacheKey}`;
                if (window.localStorage) {
                    window.localStorage.setItem(lsKey, JSON.stringify({ header, footer, ts }));
                }
            } catch (e) {
                // Ignore storage errors (quota, disabled storage, etc.)
            }
            
            this.headerImgB64 = header;
            this.footerImgB64 = footer;
            this.state.headerB64 = header;
            this.state.footerB64 = footer;
            
            console.log('Cached and set header/footer images for key:', cacheKey, 'headerB64:', !!this.state.headerB64, 'footerB64:', !!this.state.footerB64);
        } catch (e) {
            console.error('Could not load header/footer images:', e);
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