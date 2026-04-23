"""
Script review modal — pause pipeline to edit or approve script before images.
"""

import tkinter.messagebox as messagebox

import customtkinter as ctk

BG_MAIN = "#050A10"
BG_SEC = "#0A121A"
BG_CARD = "#0F1A24"
BORDER = "#1A2B3D"
ACCENT_PRI = "#0088FF"
ACCENT_SEC = "#00BFFF"
TEXT_PRI = "#E6F0FF"
TEXT_SEC = "#88AADD"
TEXT_HINT = "#4A6080"
ACCENT_GRN = "#00CC66"


class ScriptReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, script_data: dict, on_approve, on_regenerate, on_cancel):
        super().__init__(parent)
        self._on_approve = on_approve
        self._on_regenerate = on_regenerate
        self._on_cancel = on_cancel
        self._editing = False

        self.title("📝 Script Review — Step 2 of 6")
        self.geometry("800x700")
        self.minsize(700, 620)
        self.configure(fg_color=BG_MAIN)
        self.resizable(True, True)

        prompts = list(script_data.get("image_prompts") or [])
        self._total_prompts = len(prompts)

        # ── Button row — packed FIRST so it is always visible at bottom ───
        btn_row = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=BORDER)
        btn_row.pack(side="bottom", fill="x", padx=0, pady=0)

        btn_inner = ctk.CTkFrame(btn_row, fg_color="transparent")
        btn_inner.pack(fill="x", padx=16, pady=12)

        self.regen_btn = ctk.CTkButton(
            btn_inner,
            text="🔄 Regenerate Script",
            width=170,
            height=38,
            font=("Segoe UI", 13),
            fg_color="#1A1A2E",
            hover_color="#2A2A4E",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT_SEC,
            corner_radius=6,
            command=self._on_regenerate_click,
        )
        self.regen_btn.pack(side="left", padx=(0, 8))

        self.edit_btn = ctk.CTkButton(
            btn_inner,
            text="✏️ Edit Script",
            width=160,
            height=38,
            font=("Segoe UI", 13, "bold"),
            fg_color=ACCENT_PRI,
            hover_color=ACCENT_SEC,
            text_color=BG_MAIN,
            corner_radius=6,
            command=self._toggle_edit,
        )
        self.edit_btn.pack(side="left", padx=(0, 8))

        self.approve_btn = ctk.CTkButton(
            btn_inner,
            text="✅  Approve & Continue",
            height=38,
            font=("Segoe UI", 14, "bold"),
            fg_color=ACCENT_GRN,
            hover_color="#00AA55",
            text_color=BG_MAIN,
            corner_radius=6,
            command=self._on_approve_click,
        )
        self.approve_btn.pack(side="right")

        # ── Scrollable content area ───────────────────────────────────────
        scroll_area = ctk.CTkScrollableFrame(
            self,
            fg_color=BG_MAIN,
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT_PRI,
        )
        scroll_area.pack(fill="both", expand=True, padx=16, pady=(12, 6))

        # Header
        head = ctk.CTkFrame(scroll_area, fg_color="transparent")
        head.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            head,
            text="📝 Script Review",
            font=("Segoe UI", 18, "bold"),
            text_color=TEXT_PRI,
        ).pack(side="left")
        ctk.CTkLabel(
            head,
            text="Step 2 of 6",
            font=("Segoe UI", 11),
            text_color=ACCENT_SEC,
        ).pack(side="right")

        ctk.CTkLabel(
            scroll_area,
            text="Review your script. Click  ✏️ Edit Script  (below) to make changes.",
            font=("Segoe UI", 12),
            text_color=TEXT_HINT,
        ).pack(anchor="w", pady=(0, 12))

        # Divider
        ctk.CTkFrame(scroll_area, fg_color=BORDER, height=1).pack(fill="x", pady=(0, 14))

        # VIDEO TITLE
        ctk.CTkLabel(
            scroll_area,
            text="VIDEO TITLE",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w")
        self.title_entry = ctk.CTkEntry(
            scroll_area,
            font=("Segoe UI", 13),
            height=36,
            fg_color=BG_CARD,
            border_color=BORDER,
            text_color=TEXT_PRI,
            corner_radius=6,
        )
        self.title_entry.insert(0, script_data.get("title", ""))
        self.title_entry.pack(fill="x", pady=(4, 14))

        # VOICEOVER
        ctk.CTkLabel(
            scroll_area,
            text="VOICEOVER SCRIPT",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w")

        self.voiceover_box = ctk.CTkTextbox(
            scroll_area,
            height=170,
            font=("Segoe UI", 13),
            fg_color=BG_CARD,
            border_color=BORDER,
            border_width=1,
            text_color=TEXT_PRI,
            corner_radius=6,
            wrap="word",
        )
        self.voiceover_box.pack(fill="x", pady=(4, 4))
        self.voiceover_box.insert("1.0", script_data.get("voiceover", ""))
        self.voiceover_box.configure(state="disabled")

        self.word_count_label = ctk.CTkLabel(
            scroll_area,
            text="",
            font=("Segoe UI", 11),
            text_color=TEXT_HINT,
        )
        self.word_count_label.pack(anchor="w", pady=(2, 14))

        # IMAGE PROMPTS (all scenes — scrollable; was capped at 15, broke 25+ clip review)
        ctk.CTkLabel(
            scroll_area,
            text=f"IMAGE PROMPTS  —  {self._total_prompts} scene{'s' if self._total_prompts != 1 else ''}",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w", pady=(0, 6))

        self.prompt_entries: list[ctk.CTkEntry] = []
        for idx, ptxt in enumerate(prompts):
            row = ctk.CTkFrame(scroll_area, fg_color="transparent")
            row.pack(fill="x", pady=3)

            ctk.CTkLabel(
                row,
                text=f"Scene {idx + 1}",
                width=68,
                font=("Segoe UI", 11),
                text_color=TEXT_SEC,
            ).pack(side="left", padx=(0, 8))

            ent = ctk.CTkEntry(
                row,
                font=("Segoe UI", 12),
                height=32,
                fg_color=BG_CARD,
                border_color=BORDER,
                text_color=TEXT_PRI,
                corner_radius=6,
            )
            ent.insert(0, ptxt)
            ent.configure(state="disabled")
            ent.pack(side="left", fill="x", expand=True)
            self.prompt_entries.append(ent)

        # bottom padding
        ctk.CTkFrame(scroll_area, fg_color="transparent", height=10).pack()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.update_word_count()

        tb = getattr(self.voiceover_box, "_textbox", None)
        if tb is not None:
            tb.bind("<<Modified>>", self._on_voiceover_modified)

        self.after(100, self._grab_modal)

    def _grab_modal(self):
        self.grab_set()
        self.focus_set()

    def _on_voiceover_modified(self, _event=None):
        tb = getattr(self.voiceover_box, "_textbox", None)
        if tb is not None:
            if tb.edit_modified():
                self.update_word_count()
                tb.edit_modified(False)

    def update_word_count(self):
        try:
            text = self.voiceover_box.get("1.0", "end").strip()
        except Exception:
            return
        words = len(text.split()) if text else 0
        minutes = words / 130.0 if words else 0.0
        mins = int(minutes)
        secs = int(round((minutes - mins) * 60))
        self.word_count_label.configure(
            text=f"📊 Words: {words}   |   Est. Duration: ~{mins}:{secs:02d} min"
        )

    def _toggle_edit(self):
        if not self._editing:
            self._editing = True
            self.voiceover_box.configure(
                state="normal",
                border_color=ACCENT_PRI,
                border_width=2,
                fg_color="#0A1828",
            )
            for e in self.prompt_entries:
                e.configure(state="normal", border_color=ACCENT_PRI)
            self.edit_btn.configure(
                text="💾 Save Changes",
                fg_color="#004488",
                hover_color=ACCENT_PRI,
                text_color=TEXT_PRI,
            )
            self.title_entry.configure(border_color=ACCENT_PRI)
        else:
            self._editing = False
            self.voiceover_box.configure(
                state="disabled",
                border_color=BORDER,
                border_width=1,
                fg_color=BG_CARD,
            )
            for e in self.prompt_entries:
                e.configure(state="disabled", border_color=BORDER)
            self.edit_btn.configure(
                text="✏️ Edit Script",
                fg_color=ACCENT_PRI,
                hover_color=ACCENT_SEC,
                text_color=BG_MAIN,
            )
            self.title_entry.configure(border_color=BORDER)
            self.update_word_count()

    def _on_regenerate_click(self):
        if not messagebox.askyesno(
            "Regenerate Script",
            "This will generate a completely new script.\nContinue?",
            parent=self,
        ):
            return
        self.grab_release()
        self.destroy()
        self._on_regenerate()

    def _on_approve_click(self):
        title = self.title_entry.get().strip()
        voiceover = self.voiceover_box.get("1.0", "end").strip()
        merged_prompts = [e.get().strip() for e in self.prompt_entries]

        if not voiceover:
            messagebox.showwarning("Validation", "Voiceover script cannot be empty.", parent=self)
            return
        if not any(merged_prompts):
            messagebox.showwarning(
                "Validation",
                "At least one image prompt must be filled in.",
                parent=self,
            )
            return

        approved_data = {
            "title": title,
            "voiceover": voiceover,
            "image_prompts": merged_prompts,
        }

        self.grab_release()
        self.destroy()
        self._on_approve(approved_data)

    def _on_close(self):
        self.grab_release()
        self.destroy()
        self._on_cancel()
