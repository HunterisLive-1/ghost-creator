"""
gui/components/image_review.py — Image Review & Video Selection Modal
======================================================================
Shown after image generation. User sees all images in a grid and toggles
which ones should be converted to video clips via Fal.ai img2video.
"""

import customtkinter as ctk
from PIL import Image


BACKEND_OPTIONS = {
    "AnimateDiff (Cheap · $0.005/clip)": "animatediff",
    "Stable Video ($0.05/clip)": "stable_video",
    "Kling Standard ($0.14/clip)": "kling_standard",
    "Kling Pro (Best · $0.28/clip)": "kling_pro",
    "Grok Video 5s · $0.25/clip (xAI)": "grok_video_5s",
    "Grok Video 10s · $0.50/clip (xAI)": "grok_video_10s",
}
BACKEND_DISPLAY = {v: k for k, v in BACKEND_OPTIONS.items()}

DURATION_OPTIONS = ["5s", "10s"]

COLS = 4


class ImageReviewWindow(ctk.CTkToplevel):
    """
    Modal window for reviewing generated images and selecting which to
    convert to short video clips.
    """

    def __init__(
        self,
        parent,
        image_paths: list,
        scene_prompts: list,
        config: dict,
        on_continue,
        on_skip,
    ):
        super().__init__(parent)

        self.image_paths = image_paths
        self.scene_prompts = scene_prompts
        self.config = config
        self.on_continue = on_continue
        self.on_skip = on_skip

        self.toggles: dict = {}
        self.toggle_buttons: dict = {}
        self._photo_refs: list = []

        self.title("🖼️ Image Review & Video Selection")
        self.geometry("950x700")
        self.minsize(900, 650)
        self.resizable(True, True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self.grab_set)

        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_grid()
        self._build_footer()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            header,
            text="🖼️ Image Review & Video Selection",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text="Step 4 of 6",
            font=ctk.CTkFont(size=13),
            text_color="gray60",
        ).pack(side="right")

        ctk.CTkLabel(
            self,
            text="Toggle images you want converted to short video clips",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(0, 0))

    def _build_grid(self):
        scroll = ctk.CTkScrollableFrame(self, label_text="")
        scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(30, 4))

        for col in range(COLS):
            scroll.grid_columnconfigure(col, weight=1)

        for idx, image_path in enumerate(self.image_paths):
            row = idx // COLS
            col = idx % COLS
            card = self._build_image_card(scroll, image_path, idx)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="n")

    def _build_image_card(self, parent, image_path: str, index: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, corner_radius=8, width=200)

        try:
            img = Image.open(image_path)
            img.thumbnail((180, 180))
            photo = ctk.CTkImage(img, size=(180, 180))
            self._photo_refs.append(photo)
            ctk.CTkLabel(card, image=photo, text="").pack(pady=(8, 4))
        except Exception:
            ctk.CTkLabel(card, text="[Image]", width=180, height=180).pack(pady=(8, 4))

        ctk.CTkLabel(
            card,
            text=f"Scene {index + 1}",
            font=ctk.CTkFont(size=11),
        ).pack()

        toggle_var = ctk.BooleanVar(value=False)
        self.toggles[image_path] = toggle_var

        btn = ctk.CTkButton(
            card,
            text="📹 Make Video: OFF",
            fg_color="gray30",
            hover_color="gray40",
            width=170,
        )
        btn.configure(command=lambda p=image_path, v=toggle_var, b=btn: self._toggle_image(p, v, b))
        btn.pack(pady=(4, 10), padx=8, fill="x")
        self.toggle_buttons[image_path] = btn

        return card

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(1, weight=1)

        controls = ctk.CTkFrame(footer, fg_color="transparent")
        controls.grid(row=0, column=0, columnspan=3, sticky="ew")

        ctk.CTkLabel(controls, text="Backend:").pack(side="left", padx=(0, 6))

        default_backend = self.config.get("img2video_backend", "kling_standard")
        default_display = BACKEND_DISPLAY.get(default_backend, list(BACKEND_OPTIONS.keys())[2])

        self.backend_dropdown = ctk.CTkOptionMenu(
            controls,
            values=list(BACKEND_OPTIONS.keys()),
            command=self._on_backend_change,
        )
        self.backend_dropdown.set(default_display)
        self.backend_dropdown.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(controls, text="Clip Duration:").pack(side="left", padx=(0, 6))

        default_duration = self.config.get("img2video_duration", "5") + "s"
        self.duration_var = ctk.StringVar(value=default_duration)

        dur_dropdown = ctk.CTkOptionMenu(
            controls,
            values=DURATION_OPTIONS,
            variable=self.duration_var,
            command=lambda _: self._update_cost_label(),
        )
        dur_dropdown.pack(side="left")

        self.cost_label = ctk.CTkLabel(
            footer,
            text="📹 0 images selected  |  💰 Est. cost: ~$0.00",
            font=ctk.CTkFont(size=12),
        )
        self.cost_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 4))

        btn_frame = ctk.CTkFrame(footer, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=3, sticky="ew")

        ctk.CTkButton(
            btn_frame,
            text="⏭ Skip Video Conversion",
            fg_color="gray40",
            hover_color="gray50",
            command=self._on_skip,
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame,
            text="▶ Continue →",
            fg_color=("#1f6aa5", "#1f6aa5"),
            hover_color=("#1a5a8a", "#1a5a8a"),
            command=self._on_continue,
        ).pack(side="right")

    # ── Interaction handlers ──────────────────────────────────────────────────

    def _toggle_image(self, path: str, var: ctk.BooleanVar, btn: ctk.CTkButton):
        new_val = not var.get()
        var.set(new_val)
        if new_val:
            btn.configure(text="📹 Make Video: ON", fg_color=("#1f6aa5", "#1f6aa5"))
        else:
            btn.configure(text="📹 Make Video: OFF", fg_color="gray30")
        self._update_cost_label()

    def _on_backend_change(self, _):
        self._update_cost_label()

    def _update_cost_label(self):
        from modules.img2video import COST_PER_CLIP
        backend_display = self.backend_dropdown.get()
        backend_key = BACKEND_OPTIONS.get(backend_display, "kling_standard")
        selected = sum(1 for v in self.toggles.values() if v.get())
        cost = selected * COST_PER_CLIP.get(backend_key, 0.14)
        self.cost_label.configure(
            text=f"📹 {selected} images selected  |  💰 Est. cost: ~${cost:.2f}"
        )

    def _on_continue(self):
        selections = {path: var.get() for path, var in self.toggles.items()}
        backend_display = self.backend_dropdown.get()
        self.config["img2video_backend"] = BACKEND_OPTIONS.get(backend_display, "kling_standard")
        self.config["img2video_duration"] = self.duration_var.get().replace("s", "")
        self.on_continue(selections)
        self.destroy()

    def _on_skip(self):
        self.on_skip()
        self.destroy()

    def _on_close(self):
        self.on_skip()
        self.destroy()
