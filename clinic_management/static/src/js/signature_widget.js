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

        const dataURL = canvas.toDataURL("image/png");
        const base64 = dataURL.split(",")[1]; // strip "data:image/png;base64,"

        if (this.props.onChange) {
            this.props.onChange(base64); // update field value in Odoo
        }
    }
}

registry.category("fields").add("draw_canvas", {
    component: DrawCanvasWidget,
});
