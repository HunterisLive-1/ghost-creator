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
ACCENT_GRN = "#00CC66"


class ScriptReviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, script_data: dict, on_approve, on_regenerate, on_cancel):
        super().__init__(parent)
        self._on_approve = on_approve
        self._on_regenerate = on_regenerate
        self._on_cancel = on_cancel
        self._editing = False

        self.title("Script Review")
        self.geometry("760x640")
        self.minsize(700, 600)
        self.configure(fg_color=BG_MAIN)

        self._original_prompts_full = list(script_data.get("image_prompts") or [])
        prompts = list(self._original_prompts_full)
        self._total_prompts = len(prompts)
        self._display_cap = 15
        if len(prompts) > self._display_cap:
            prompts = prompts[: self._display_cap]

        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(
            head,
            text="📝 Script Review",
            font=("Segoe UI", 18, "bold"),
            text_color=TEXT_PRI,
        ).pack(anchor="w")
        ctk.CTkLabel(
            head,
            text="Review your script before generating images.",
            font=("Segoe UI", 12),
            text_color=TEXT_SEC,
        ).pack(anchor="w")
        ctk.CTkLabel(
            head,
            text="Step 2 of 6",
            font=("Segoe UI", 11),
            text_color=ACCENT_SEC,
        ).pack(anchor="ne")

        body = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=8, border_width=1, border_color=BORDER)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        inner = ctk.CTkFrame(body, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(inner, text="VIDEO TITLE", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w")
        self.title_entry = ctk.CTkEntry(
            inner,
            font=("Segoe UI", 13),
            fg_color=BG_CARD,
            border_color=BORDER,
            text_color=TEXT_PRI,
        )
        self.title_entry.insert(0, script_data.get("title", ""))
        self.title_entry.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(inner, text="VOICEOVER SCRIPT", font=("Segoe UI", 11, "bold"), text_color=TEXT_SEC).pack(anchor="w")
        self.voiceover_box = ctk.CTkTextbox(
            inner,
            height=200,
            font=("Segoe UI", 13),
            fg_color=BG_CARD,
            border_color=BORDER,
            text_color=TEXT_PRI,
        )
        self.voiceover_box.pack(fill="x", pady=(4, 4))
        self.voiceover_box.insert("1.0", script_data.get("voiceover", ""))
        self.voiceover_box.configure(state="disabled")

        self.word_count_label = ctk.CTkLabel(
            inner,
            text="",
            font=("Segoe UI", 12),
            text_color=TEXT_SEC,
        )
        self.word_count_label.pack(anchor="w", pady=(0, 12))

        cap_note = ""
        if self._total_prompts > self._display_cap:
            cap_note = f" (showing first {self._display_cap} of {self._total_prompts})"
        ctk.CTkLabel(
            inner,
            text=f"IMAGE PROMPTS ({len(prompts)} scenes){cap_note}",
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w")

        self.prompt_scroll = ctk.CTkScrollableFrame(
            inner,
            fg_color=BG_CARD,
            height=220,
            border_width=1,
            border_color=BORDER,
        )
        self.prompt_scroll.pack(fill="both", expand=True, pady=(4, 12))

        self.prompt_entries: list[ctk.CTkEntry] = []
        for idx, ptxt in enumerate(prompts):
            row = ctk.CTkFrame(self.prompt_scroll, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(
                row,
                text=f"Scene {idx + 1}:",
                width=72,
                font=("Segoe UI", 11),
                text_color=TEXT_SEC,
            ).pack(side="left", padx=(0, 8))
            ent = ctk.CTkEntry(
                row,
                font=("Segoe UI", 12),
                fg_color=BG_MAIN,
                border_color=BORDER,
                text_color=TEXT_PRI,
            )
            ent.insert(0, ptxt)
            ent.configure(state="disabled")
            ent.pack(side="left", fill="x", expand=True)
            self.prompt_entries.append(ent)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 16))

        self.regen_btn = ctk.CTkButton(
            btn_row,
            text="🔄 Regenerate",
            width=140,
            fg_color=BG_CARD,
            hover_color=BORDER,
            text_color=TEXT_PRI,
            command=self._on_regenerate_click,
        )
        self.regen_btn.pack(side="left", padx=(0, 8))

        self.edit_btn = ctk.CTkButton(
            btn_row,
            text="✏️ Edit Script",
            width=160,
            fg_color=BG_CARD,
            hover_color=BORDER,
            text_color=TEXT_PRI,
            command=self._toggle_edit,
        )
        self.edit_btn.pack(side="left", padx=(0, 8))

        self.approve_btn = ctk.CTkButton(
            btn_row,
            text="✅ Approve & Continue",
            width=200,
            fg_color=ACCENT_GRN,
            hover_color="#00AA55",
            text_color=BG_MAIN,
            command=self._on_approve_click,
        )
        self.approve_btn.pack(side="right")

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
        text = self.voiceover_box.get("1.0", "end").strip()
        words = len(text.split())
        minutes = words / 130.0 if words else 0.0
        mins = int(minutes)
        secs = int(round((minutes - mins) * 60))
        self.word_count_label.configure(
            text=f"📊 Words: {words}  |  Est. Duration: ~{mins}:{secs:02d} min"
        )

    def _toggle_edit(self):
        if not self._editing:
            self._editing = True
            self.voiceover_box.configure(state="normal", border_color=ACCENT_PRI, border_width=2)
            for e in self.prompt_entries:
                e.configure(state="normal")
            self.edit_btn.configure(text="💾 Save Changes")
        else:
            self._editing = False
            self.voiceover_box.configure(state="disabled", border_color=BORDER, border_width=1)
            for e in self.prompt_entries:
                e.configure(state="disabled")
            self.edit_btn.configure(text="✏️ Edit Script")
            self.update_word_count()

    def _on_regenerate_click(self):
        if not messagebox.askyesno(
            "Regenerate script",
            "This will generate a completely new script. Continue?",
            parent=self,
        ):
            return
        self.grab_release()
        self.destroy()
        self._on_regenerate()

    def _on_approve_click(self):
        title = self.title_entry.get().strip()
        voiceover = self.voiceover_box.get("1.0", "end").strip()
        image_prompts = [e.get().strip() for e in self.prompt_entries]

        merged_prompts = list(image_prompts)
        if self._total_prompts > self._display_cap:
            tail = self._original_prompts_full[self._display_cap :]
            merged_prompts = list(image_prompts) + [str(x) for x in tail]

        if not voiceover:
            messagebox.showwarning("Validation", "Voiceover cannot be empty.", parent=self)
            return
        if not any(merged_prompts):
            messagebox.showwarning(
                "Validation",
                "At least one image prompt must be non-empty.",
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
