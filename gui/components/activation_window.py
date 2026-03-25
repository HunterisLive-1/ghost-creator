"""
gui/components/activation_window.py — Ghost Creator AI License Activation
"""

import sys
import threading
import webbrowser

import customtkinter as ctk

# Matches Ghost Creator blue palette
BG_MAIN    = "#050A10"
BG_SEC     = "#0A121A"
BG_CARD    = "#0F1A24"
BORDER     = "#1A2B3D"
ACCENT_PRI = "#0088FF"
ACCENT_SEC = "#00BFFF"
ACCENT_RED = "#FF4444"
ACCENT_GRN = "#00CC66"
TEXT_PRI   = "#E6F0FF"
TEXT_SEC   = "#88AADD"
TEXT_HINT  = "#4A6080"


class ActivationWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_activated):
        super().__init__(parent)
        self.on_activated = on_activated

        self.title("Ghost Creator AI — Activation")
        self.geometry("480x330")
        self.resizable(False, False)
        self.configure(fg_color=BG_MAIN)

        # Modal: block interaction with parent window
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

        # Centre on screen after widgets are ready
        self.after(50, self._centre)

    def _centre(self):
        self.update_idletasks()
        w, h = 480, 330
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # ── Top accent bar ──────────────────────────────────────────────────
        ctk.CTkFrame(self, height=2, fg_color=ACCENT_PRI, corner_radius=0).pack(fill="x")

        # ── Header ─────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header,
            text="👻  GHOST CREATOR AI  —  Activation",
            font=("Orbitron", 14, "bold"),
            text_color=ACCENT_PRI,
        ).pack(pady=12)

        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x")

        # ── Body ────────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=(18, 10))

        ctk.CTkLabel(
            body,
            text="Enter your license key to activate Ghost Creator AI",
            font=("Share Tech Mono", 12),
            text_color=TEXT_SEC,
        ).pack(anchor="w", pady=(0, 10))

        # Key entry row
        ctk.CTkLabel(
            body,
            text="LICENSE KEY:",
            font=("Share Tech Mono", 11, "bold"),
            text_color=TEXT_SEC,
        ).pack(anchor="w")

        key_row = ctk.CTkFrame(body, fg_color="transparent")
        key_row.pack(fill="x", pady=(4, 14))

        self.key_entry = ctk.CTkEntry(
            key_row,
            placeholder_text="GHOST-XXXX-XXXX-XXXX-XXXX",
            font=("Share Tech Mono", 13),
            fg_color=BG_CARD,
            border_color=BORDER,
            text_color=TEXT_PRI,
            placeholder_text_color=TEXT_HINT,
            corner_radius=0,
            height=36,
        )
        self.key_entry.pack(fill="x")
        self.key_entry.bind("<FocusIn>",  lambda e: self.key_entry.configure(border_width=2, border_color=ACCENT_PRI))
        self.key_entry.bind("<FocusOut>", lambda e: self.key_entry.configure(border_width=1, border_color=BORDER))
        self.key_entry.bind("<Return>", lambda e: self._on_activate_click())

        # Activate button
        self.activate_btn = ctk.CTkButton(
            body,
            text="🔑  Activate",
            font=("Orbitron", 13, "bold"),
            text_color=BG_MAIN,
            fg_color=ACCENT_PRI,
            hover_color=ACCENT_SEC,
            corner_radius=0,
            height=40,
            command=self._on_activate_click,
        )
        self.activate_btn.pack(fill="x", pady=(0, 14))

        # Purchase link
        link_frame = ctk.CTkFrame(body, fg_color="transparent")
        link_frame.pack(anchor="w")
        ctk.CTkLabel(
            link_frame,
            text="Don't have a key?  👉",
            font=("Share Tech Mono", 11),
            text_color=TEXT_SEC,
        ).pack(side="left")
        link_btn = ctk.CTkButton(
            link_frame,
            text="Get Ghost Creator at getmaya.online",
            font=("Share Tech Mono", 11, "bold"),
            text_color=ACCENT_SEC,
            fg_color="transparent",
            hover_color=BG_CARD,
            border_width=0,
            cursor="hand2",
            command=lambda: webbrowser.open("https://getmaya.online"),
        )
        link_btn.pack(side="left")

        # Divider
        ctk.CTkFrame(body, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x", pady=(12, 8))

        # Status label
        self.status_label = ctk.CTkLabel(
            body,
            text="",
            font=("Share Tech Mono", 12),
            text_color=TEXT_HINT,
            anchor="w",
        )
        self.status_label.pack(anchor="w")

        # ── Bottom accent bar ───────────────────────────────────────────────
        ctk.CTkFrame(self, height=2, fg_color=BORDER, corner_radius=0).pack(fill="x", side="bottom")

    # ── Button logic ─────────────────────────────────────────────────────────
    def _on_activate_click(self):
        key = self.key_entry.get().strip()
        if not key:
            self.status_label.configure(text="⚠️  Please enter your license key.", text_color=ACCENT_RED)
            return
        self.status_label.configure(text="⟳  Verifying…", text_color=TEXT_HINT)
        self.activate_btn.configure(state="disabled", text="⟳  Verifying…")
        threading.Thread(target=self._do_activate, args=(key,), daemon=True).start()

    def _do_activate(self, key: str):
        from core.license import activate_license
        success, message = activate_license(key)
        self.after(0, self._on_result, success, message)

    def _on_result(self, success: bool, message: str):
        if success:
            self.status_label.configure(text=f"✅  {message}", text_color=ACCENT_GRN)
            self.activate_btn.configure(text="✅  Activated!", state="disabled")
            self.after(1200, self._finish)
        else:
            self.status_label.configure(text=f"❌  {message}", text_color=ACCENT_RED)
            self.activate_btn.configure(state="normal", text="🔑  Activate")

    def _finish(self):
        self.grab_release()
        self.destroy()
        self.on_activated()

    def _on_close(self):
        """Closing the activation window exits the entire application."""
        sys.exit(0)
