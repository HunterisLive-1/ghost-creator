"""
gui/tabs/pipeline_tab.py — Pipeline Tab Cyberpunk
"""

import queue
import math
import tkinter as tk
from datetime import datetime
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox

from PIL import Image
import customtkinter as ctk

from core.config_manager import config

# === BLUE AI PALETTE ===
BG_MAIN     = "#050A10"
BG_SEC      = "#0A121A"
BG_CARD     = "#0F1A24"
BORDER      = "#1A2B3D"
ACCENT_PRI  = "#0088FF"
ACCENT_SEC  = "#00BFFF"
ACCENT_RED  = "#FF4444"
ACCENT_WARN = "#FFB800"
TEXT_PRI    = "#E6F0FF"
TEXT_SEC    = "#88AADD"

STEPS = ["Research", "Script", "Voice", "Images", "Video", "Upload"]

class PipelineTab(ctk.CTkFrame):
    def __init__(self, master, progress_queue: queue.Queue, app_ref, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.progress_queue = progress_queue
        self.app_ref = app_ref
        self.runner = None
        self.pipeline_running = False
        self.custom_image_paths: list[str] = []
        self._thumb_photo_refs: list = []

        self._step_states = ["pending"] * 6
        self._current_step_idx = -1
        self._progress_val = 0.0

        self._build_topic_row()
        self._build_duration_row()
        self._build_image_source_section()
        self._build_control_row()
        self._build_progress_section()
        self._build_log_section()
        self._build_output_preview()

        # Uplink status
        self._uplink_lbl = ctk.CTkLabel(
            self, text="UPLINK: [No Profile]",
            font=("Orbitron", 12, "bold"), text_color=ACCENT_SEC
        )
        self._uplink_lbl.pack(side="bottom", anchor="se", padx=20, pady=10)

        self._poll_queue()

    # ── Topic Input ───────────────────────────────────────────────────────
    def _build_topic_row(self):
        frame = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(20, 10))
        
        # Corner brackets (using canvas)
        self._add_corner_brackets(frame)

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(inner, text="NEURAL PROMPT:", font=("Share Tech Mono", 14), text_color=ACCENT_PRI).pack(side="left")

        self._topic_entry = ctk.CTkEntry(
            inner, placeholder_text="Enter parameters or leave blank for auto-matrix...",
            width=500, font=("Share Tech Mono", 13),
            fg_color=BG_MAIN, border_color=ACCENT_PRI, text_color=TEXT_PRI,
            corner_radius=0, border_width=1
        )
        self._topic_entry.pack(side="left", padx=15)
        
        # entry focus glow effect 
        self._topic_entry.bind("<FocusIn>", lambda e: self._topic_entry.configure(border_width=2))
        self._topic_entry.bind("<FocusOut>", lambda e: self._topic_entry.configure(border_width=1))

        self._auto_var = ctk.BooleanVar(value=False)
        self._auto_check = ctk.CTkCheckBox(
            inner, text="ENGAGE AUTO-MATRIX",
            variable=self._auto_var,
            font=("Share Tech Mono", 13, "bold"), text_color=TEXT_SEC,
            fg_color=BG_MAIN, border_color=ACCENT_PRI, hover_color=BG_CARD,
            checkmark_color=ACCENT_PRI, corner_radius=0,
            command=self._toggle_auto,
        )
        self._auto_check.pack(side="left", padx=15)

    def _toggle_auto(self):
        if self._auto_var.get():
            self._topic_entry.configure(state="disabled")
            self._auto_check.configure(text_color=ACCENT_PRI)
        else:
            self._topic_entry.configure(state="normal")
            self._auto_check.configure(text_color=TEXT_SEC)

    # ── Target duration (pipeline tab) ───────────────────────────────────
    def _build_duration_row(self):
        frame = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(
            inner,
            text="TARGET DURATION (SEC):",
            font=("Share Tech Mono", 14),
            text_color=ACCENT_PRI,
        ).pack(side="left")

        td0 = int(config.get("target_duration", 60))
        self._duration_var = tk.DoubleVar(value=float(max(60, min(td0, 600))))
        self._duration_slider = ctk.CTkSlider(
            inner,
            from_=60,
            to=600,
            number_of_steps=540,
            variable=self._duration_var,
            width=400,
            fg_color=BORDER,
            progress_color=ACCENT_PRI,
            button_color=ACCENT_SEC,
            button_hover_color=ACCENT_PRI,
            command=self._on_duration_slider,
        )
        self._duration_slider.pack(side="left", padx=15, fill="x", expand=True)

        self._duration_lbl = ctk.CTkLabel(
            inner,
            text=f"{int(self._duration_var.get())}s",
            font=("Share Tech Mono", 13, "bold"),
            text_color=ACCENT_SEC,
            width=56,
        )
        self._duration_lbl.pack(side="left")

    def _on_duration_slider(self, _val=None):
        v = int(self._duration_var.get())
        self._duration_lbl.configure(text=f"{v}s")
        config.set("target_duration", max(60, min(v, 600)))
        self._update_needed_images_hint()

    def _update_needed_images_hint(self):
        if not hasattr(self, "_need_label"):
            return
        d = int(self._duration_var.get())
        n = max(6, min(d // 10, 40))
        self._need_label.configure(text=f"Need: {n} images for {d}s")

    # ── Image source (AI vs custom) ───────────────────────────────────────
    def _build_image_source_section(self):
        frame = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        ctk.CTkLabel(
            inner,
            text="IMAGE SOURCE",
            font=("Share Tech Mono", 14, "bold"),
            text_color=ACCENT_PRI,
        ).pack(anchor="w")

        seg_vals = ["🤖 AI Generate", "📁 My Own Images"]
        self._img_source_seg = ctk.CTkSegmentedButton(
            inner,
            values=seg_vals,
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_PRI,
            fg_color=BG_MAIN,
            selected_color=ACCENT_PRI,
            selected_hover_color=ACCENT_SEC,
            unselected_color=BG_CARD,
            unselected_hover_color=BORDER,
            corner_radius=0,
            command=self._on_image_source_segment,
        )
        init_src = config.get("image_source", "ai_generate")
        self._img_source_seg.set(
            "📁 My Own Images" if init_src == "custom_images" else "🤖 AI Generate"
        )
        self._img_source_seg.pack(anchor="w", pady=(8, 4))

        self._image_panel = ctk.CTkFrame(inner, fg_color=BG_CARD, corner_radius=0, border_width=1, border_color=BORDER)
        top = ctk.CTkFrame(self._image_panel, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 6))

        self._img_count_lbl = ctk.CTkLabel(
            top,
            text="📁 My Images (0 selected)",
            font=("Share Tech Mono", 12, "bold"),
            text_color=TEXT_SEC,
        )
        self._img_count_lbl.pack(side="left")

        ctk.CTkButton(
            top,
            text="+ Add Images",
            width=120,
            font=("Share Tech Mono", 11, "bold"),
            fg_color=ACCENT_PRI,
            hover_color=ACCENT_SEC,
            text_color=BG_MAIN,
            corner_radius=0,
            command=self._add_custom_images,
        ).pack(side="right")

        self._thumb_scroll = ctk.CTkScrollableFrame(
            self._image_panel,
            fg_color=BG_MAIN,
            height=100,
            orientation="horizontal",
            border_width=1,
            border_color=BORDER,
        )
        self._thumb_scroll.pack(fill="x", padx=10, pady=(0, 8))

        self._empty_thumb_lbl = ctk.CTkLabel(
            self._thumb_scroll,
            text="No images selected yet  →  thumbnails show here when added",
            font=("Share Tech Mono", 11),
            text_color=TEXT_SEC,
        )
        self._empty_thumb_lbl.pack(pady=24)

        bot = ctk.CTkFrame(self._image_panel, fg_color="transparent")
        bot.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            bot,
            text="🗑️ Clear All",
            width=100,
            font=("Share Tech Mono", 11),
            fg_color="#331111",
            hover_color=ACCENT_RED,
            text_color=TEXT_PRI,
            corner_radius=0,
            command=self._clear_custom_images,
        ).pack(side="left")

        self._need_label = ctk.CTkLabel(
            bot,
            text="",
            font=("Share Tech Mono", 11),
            text_color=ACCENT_WARN,
        )
        self._need_label.pack(side="right")

        self._update_needed_images_hint()

        if init_src == "custom_images":
            self._image_panel.pack(fill="x", pady=(8, 0))
        else:
            self._image_panel.pack_forget()

        saved_paths = config.get("custom_image_paths", [])
        if isinstance(saved_paths, list) and saved_paths:
            self.custom_image_paths = [str(x) for x in saved_paths]
            self._refresh_thumbnails()

    def _on_image_source_segment(self, value: str):
        if "My Own" in value:
            config.set("image_source", "custom_images")
            self._image_panel.pack(fill="x", pady=(8, 0))
        else:
            config.set("image_source", "ai_generate")
            config.set("custom_image_paths", [])
            self.custom_image_paths = []
            self._refresh_thumbnails()
            self._image_panel.pack_forget()

    def _add_custom_images(self):
        paths = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        for p in paths:
            if p and p not in self.custom_image_paths:
                self.custom_image_paths.append(p)
        self._refresh_thumbnails()

    def _clear_custom_images(self):
        self.custom_image_paths = []
        self._refresh_thumbnails()

    def _refresh_thumbnails(self):
        self._thumb_photo_refs.clear()
        for w in self._thumb_scroll.winfo_children():
            w.destroy()

        n = len(self.custom_image_paths)
        self._img_count_lbl.configure(text=f"📁 My Images ({n} selected)")
        config.set("custom_image_paths", list(self.custom_image_paths))

        if not self.custom_image_paths:
            self._empty_thumb_lbl = ctk.CTkLabel(
                self._thumb_scroll,
                text="No images selected yet  →  thumbnails show here when added",
                font=("Share Tech Mono", 11),
                text_color=TEXT_SEC,
            )
            self._empty_thumb_lbl.pack(pady=24)
            return

        for path in self.custom_image_paths:
            self._add_thumbnail(path)

    def _add_thumbnail(self, path: str):
        try:
            img = Image.open(path).resize((80, 80), Image.LANCZOS)
        except OSError:
            return
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 80))
        self._thumb_photo_refs.append(photo)

        fr = ctk.CTkFrame(self._thumb_scroll, fg_color=BG_CARD, width=96, height=96)
        fr.pack(side="left", padx=6, pady=8)

        ctk.CTkLabel(fr, image=photo, text="").pack(padx=4, pady=(4, 0))
        ctk.CTkButton(
            fr,
            text="✕",
            width=22,
            height=20,
            font=("Arial", 10, "bold"),
            fg_color="#442222",
            hover_color=ACCENT_RED,
            corner_radius=0,
            command=lambda p=path: self._remove_image(p),
        ).pack(pady=(2, 4))

    def _remove_image(self, path: str):
        self.custom_image_paths = [p for p in self.custom_image_paths if p != path]
        self._refresh_thumbnails()

    # ── Run/Stop Controls ─────────────────────────────────────────────────
    def _build_control_row(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=10)

        # Run Button
        self._run_btn = ctk.CTkButton(
            frame, text="INITIALIZE SEQUENCE",
            font=("Orbitron", 14, "bold"), text_color=ACCENT_SEC,
            fg_color="#001833", hover_color=ACCENT_SEC,
            border_color=ACCENT_SEC, border_width=1, corner_radius=0,
            height=45, width=250,
            command=self._on_run,
        )
        self._run_btn.pack(side="left")

        # Stop Button
        self._stop_btn = ctk.CTkButton(
            frame, text="ABORT",
            font=("Orbitron", 14, "bold"), text_color=ACCENT_RED,
            fg_color="#330000", hover_color=ACCENT_RED,
            border_color=ACCENT_RED, border_width=1, corner_radius=0,
            height=45, width=150,
            state="disabled",
            command=self._on_stop,
        )
        self._stop_btn.pack(side="left", padx=15)

    # ── Progress Section ──────────────────────────────────────────────────
    def _build_progress_section(self):
        frame = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=20, pady=10)
        self._add_corner_brackets(frame)

        # Hexagon Steps via Canvas
        self.steps_canvas = tk.Canvas(frame, bg=BG_SEC, height=80, highlightthickness=0)
        self.steps_canvas.pack(fill="x", padx=20, pady=(20, 0))

        # Progress bar via Canvas
        bar_frame = ctk.CTkFrame(frame, fg_color="transparent")
        bar_frame.pack(fill="x", padx=20, pady=(10, 20))
        
        self.prog_canvas = tk.Canvas(bar_frame, bg=BG_MAIN, height=16, highlightthickness=1, highlightbackground=ACCENT_PRI)
        self.prog_canvas.pack(side="left", fill="x", expand=True, padx=(0, 15))
        
        self._progress_pct = ctk.CTkLabel(
            bar_frame, text="0%", font=("Orbitron", 16, "bold"),
            text_color=ACCENT_PRI, width=50,
        )
        self._progress_pct.pack(side="right")
        
        self.bind("<Configure>", self._redraw_steps_and_bar)

    def _draw_hexagon(self, canvas, x, y, r, outline, fill="", tags=""):
        points = []
        for i in range(6):
            angle_deg = 60 * i - 30
            angle_rad = math.pi / 180 * angle_deg
            points.append(x + r * math.cos(angle_rad))
            points.append(y + r * math.sin(angle_rad))
        return canvas.create_polygon(points, outline=outline, fill=fill, width=2, tags=tags)

    def _redraw_steps_and_bar(self, event=None):
        w = self.steps_canvas.winfo_width()
        if w < 50: return
        self.steps_canvas.delete("all")
        
        n = len(STEPS)
        spacing = w / n
        r = 16
        
        self._hex_centers = []
        for i in range(n):
            cx = spacing * i + spacing / 2
            cy = 30
            self._hex_centers.append((cx, cy))
            
            state = self._step_states[i]
            if state == "pending":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, BORDER, BG_MAIN, "hex")
            elif state == "active":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, ACCENT_PRI, BG_MAIN, "hex")
                # Pulsing ring drawn in animation loop
            elif state == "done":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, ACCENT_SEC, ACCENT_SEC, "hex")
                self.steps_canvas.create_text(cx, cy, text="✓", fill=BG_MAIN, font=("Courier New", 12, "bold"))
            elif state == "error":
                self._draw_hexagon(self.steps_canvas, cx, cy, r, ACCENT_RED, ACCENT_RED, "hex")
                self.steps_canvas.create_text(cx, cy, text="✗", fill=BG_MAIN, font=("Courier New", 12, "bold"))
                
            color = ACCENT_PRI if state != "pending" else TEXT_SEC
            self.steps_canvas.create_text(cx, cy + 30, text=STEPS[i].upper(), fill=color, font=("Share Tech Mono", 10, "bold"))
            
            # Connecting dashes
            if i < n - 1:
                next_x = spacing * (i + 1) + spacing / 2
                dash_color = ACCENT_PRI if state in ["done", "active"] else BORDER
                dash_tag = "dash_active" if state == "active" else "dash"
                self.steps_canvas.create_line(cx + r + 5, cy, next_x - r - 5, cy, fill=dash_color, width=2, 
                                              dash=(4, 4), tags=dash_tag)
                
        self._redraw_progress_bar()

    def _redraw_progress_bar(self):
        w = self.prog_canvas.winfo_width()
        h = self.prog_canvas.winfo_height()
        if w < 10: return
        
        self.prog_canvas.delete("bar")
        
        fill_w = w * self._progress_val
        if fill_w > 0:
            # Simulate gradient from ACCENT_SEC to ACCENT_PRI
            # Split into 20 vertical rectangles
            segments = 20
            seg_w = fill_w / segments
            # Colors: approx from #FFCC00 to #FF9900
            for i in range(segments):
                ratio = i / (segments - 1) if segments > 1 else 0
                r = 0xFF
                g = int(0xCC * (1-ratio) + 0x99 * ratio)
                b = 0x00
                color = f"#{r:02x}{g:02x}{b:02x}"
                self.prog_canvas.create_rectangle(i*seg_w, 0, (i+1)*seg_w, h, fill=color, outline="", tags="bar")

    # ── Live Log ──────────────────────────────────────────────────────────
    def _build_log_section(self):
        frame = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        frame.pack(fill="both", expand=True, padx=20, pady=10)
        self._add_corner_brackets(frame)

        self.log_lbl = ctk.CTkLabel(frame, text="[ TERMINAL OUTPUT ] ▋",
                     font=("Share Tech Mono", 14, "bold"),
                     text_color=ACCENT_PRI)
        self.log_lbl.pack(anchor="w", padx=20, pady=(15, 5))

        self._log_box = ctk.CTkTextbox(
            frame, font=("Consolas", 12),
            fg_color="#020608", border_color=BORDER, border_width=1, corner_radius=0,
            state="disabled"
        )
        self._log_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self._log_box.tag_config("INFO", foreground=TEXT_SEC)
        self._log_box.tag_config("SUCCESS", foreground=ACCENT_SEC)
        self._log_box.tag_config("ERROR", foreground=ACCENT_RED)
        self._log_box.tag_config("WARNING", foreground=ACCENT_WARN)

    # ── Output Preview ────────────────────────────────────────────────────
    def _build_output_preview(self):
        self._output_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, border_color=ACCENT_SEC, border_width=1)

        self._output_label = ctk.CTkLabel(
            self._output_frame, text="",
            font=("Share Tech Mono", 14, "bold"), text_color=ACCENT_SEC
        )
        self._output_label.pack(padx=20, pady=(15, 5))

        self._open_btn = ctk.CTkButton(
            self._output_frame, text=">> ACCESS DATABANK",
            font=("Orbitron", 12, "bold"), text_color=BG_MAIN,
            fg_color=ACCENT_PRI, hover_color=TEXT_PRI, corner_radius=0,
            command=self._open_output_folder,
        )
        self._open_btn.pack(padx=20, pady=(5, 15))

    def _open_output_folder(self):
        out_dir = config.get("pipeline.output_folder", "output")
        from pathlib import Path
        import subprocess
        full_path = Path(config.path).parent / out_dir
        if full_path.exists():
            subprocess.Popen(["explorer", str(full_path)])

    def update_uplink_status(self, name):
        self._uplink_lbl.configure(text=f"UPLINK: [{name}]")

    # ── Corner brackets ───────────────────────────────────────────────────
    def _add_corner_brackets(self, frame):
        """Draws 4 corner brackets on a frame using a translucent canvas layer."""
        pass

    # ── Queue Polling ─────────────────────────────────────────────────────
    def _poll_queue(self):
        try:
            while True:
                msg = self.progress_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
            
        self.after(100, _poll_queue_wrapper, self)

    def _handle_message(self, msg: dict):
        rid = msg.get("run_id")
        if rid is not None and rid != getattr(self, "_pipeline_run_id", 0):
            return

        step = msg.get("step", 0)
        message = msg.get("message", "")
        level = msg.get("level", "INFO")
        done = msg.get("done", False)
        output_path = msg.get("output_path", "")

        # prefixes
        prefix = ""
        if level == "SUCCESS": prefix = "[OK] "
        if level == "ERROR": prefix = "[ERR] "
        if level == "WARNING": prefix = "[WARN] "

        self._append_log(prefix + message, level)

        if 1 <= step <= 6:
            for i in range(step - 1):
                self._step_states[i] = "done"
            if level == "ERROR":
                self._step_states[step - 1] = "error"
            elif level == "SUCCESS":
                self._step_states[step - 1] = "done"
            else:
                self._step_states[step - 1] = "active"
            
            p = step / 6 if level == "SUCCESS" else (step - 1)/6 + 1/12
            self._progress_val = p
            self._progress_pct.configure(text=f"{int(p * 100)}%")
            self._redraw_steps_and_bar()

        if done:
            self.pipeline_running = False
            if level != "ERROR":
                self._progress_val = 1.0
                self._progress_pct.configure(text="100%")
                self._step_states = ["done"] * 6
                self._redraw_steps_and_bar()
                self.app_ref.set_system_state("READY")

            if output_path:
                self._output_label.configure(text=f">> NEURAL RENDER COMPLETE: {output_path}")
                self._output_frame.pack(fill="x", padx=20, pady=5)

            self._run_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled", border_color=ACCENT_RED)
            self.app_ref.set_system_state("READY" if level != "ERROR" else "ERROR")

    def _append_log(self, text: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"[{timestamp}] ", level)
        self._log_box.insert("end", f"{text}\n", level)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # ── Controls ──────────────────────────────────────────────────────────
    def _on_run(self):
        src = config.get("image_source", "ai_generate")
        if src == "custom_images" and not self.custom_image_paths:
            messagebox.showerror(
                "Custom images",
                "Select at least one image, or switch to AI Generate.",
                parent=self.winfo_toplevel(),
            )
            return
        self._run_pipeline_internal()

    def _run_pipeline_internal(self):
        from core.pipeline_runner import PipelineRunner

        config.set("custom_image_paths", list(self.custom_image_paths))

        self._pipeline_run_id = getattr(self, "_pipeline_run_id", 0) + 1

        self.app_ref.set_system_state("PROCESSING")
        self._progress_val = 0.0
        self._progress_pct.configure(text="0%")
        self._step_states = ["pending"] * 6
        self._redraw_steps_and_bar()
        self._output_frame.pack_forget()
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        topic = None
        if not self._auto_var.get():
            topic = self._topic_entry.get().strip() or None

        self.pipeline_running = True
        self.runner = PipelineRunner(self.progress_queue, run_id=self._pipeline_run_id)
        self.runner.start(topic)

        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")

        self.after(500, self._check_for_review_needed)

    def _check_for_review_needed(self):
        if not self.pipeline_running:
            return
        if self.runner and getattr(self.runner, "waiting_for_script_review", False):
            self._show_script_review_window()
            return
        self.after(500, self._check_for_review_needed)

    def _show_script_review_window(self):
        from gui.components.script_review import ScriptReviewWindow

        script_data = self.runner.pending_script_data
        if not script_data:
            self.after(500, self._check_for_review_needed)
            return

        def on_approve(approved_data):
            self.runner.approve_script(approved_data)
            self._append_log("[OK] Script approved ✓ — generating images...", "SUCCESS")
            self.after(500, self._check_for_review_needed)

        def on_regenerate():
            self.runner.cancel_pipeline_from_review()
            self._append_log("[INFO] Regenerating script...", "INFO")
            self.after(400, self._run_pipeline_internal)

        def on_cancel():
            self.runner.cancel_pipeline_from_review()
            self._on_pipeline_stopped()

        ScriptReviewWindow(self.winfo_toplevel(), script_data, on_approve, on_regenerate, on_cancel)

    def _on_pipeline_stopped(self):
        self.pipeline_running = False
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled", border_color=ACCENT_RED)
        self.app_ref.set_system_state("READY")

    def _on_stop(self):
        self.pipeline_running = False
        if self.runner:
            self.runner.stop()
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled", border_color=ACCENT_RED)
        self.app_ref.set_system_state("READY")

# Global wrapper functions for after() loops to avoid unbound method GC issues
def _poll_queue_wrapper(obj):
    if hasattr(obj, '_poll_queue'): obj._poll_queue()
