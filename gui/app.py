"""
gui/app.py — Ghost Creator AI v4.1 Neural Interface
"""
import queue
import sys
import tkinter as tk
from pathlib import Path
import customtkinter as ctk

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config import APP_VERSION
from core.config_manager import config
from gui.tabs.settings_tab import SettingsTab
from gui.tabs.documentary_tab import DocumentaryTab
from gui.tabs.history_tab import HistoryTab

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

ctk.set_appearance_mode("dark")

class GhostCreatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Ghost Creator AI v{APP_VERSION} — Neural Interface")
        self.geometry("1100x800")
        self.minsize(800, 600)
        self.configure(fg_color=BG_MAIN)

        if getattr(sys, 'frozen', False):
            base_path = Path(getattr(sys, '_MEIPASS', _project_root))
        else:
            base_path = _project_root

        icon_path = base_path / "icon.ico"
        if icon_path.exists():
            self.iconbitmap(str(icon_path))
        else:
            fallback_path = base_path / "assets" / "ghost_icon.ico"
            if fallback_path.exists():
                self.iconbitmap(str(fallback_path))

        self._check_license_on_start()

    # ── License gate ─────────────────────────────────────────────────────────
    def _check_license_on_start(self):
        from core.license import is_licensed
        valid, _message = is_licensed()
        if valid:
            self._init_main_ui()
        else:
            # Hide main window until license is provided
            self.withdraw()
            from gui.components.activation_window import ActivationWindow
            ActivationWindow(self, on_activated=self._on_license_activated)

    def _on_license_activated(self):
        self.deiconify()
        self._init_main_ui()

    # ── Main UI (built only after license is confirmed) ───────────────────────
    def _init_main_ui(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        self._build_top_bar()
        self._build_bottom_bar()
        self._build_tabs()

    # --- UI Layout ---
    def _build_top_bar(self):
        self.sys_state = "READY"
        
        bar = ctk.CTkFrame(self.main_container, fg_color=BG_MAIN, corner_radius=0)
        bar.pack(fill="x", pady=(10, 0))
        
        ctk.CTkLabel(bar, text="👻 GHOST CREATOR AI", font=("Orbitron", 16, "bold"), text_color=ACCENT_PRI).pack(side="left", padx=20)
        
        badge = ctk.CTkFrame(bar, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=ACCENT_PRI)
        badge.pack(side="left", padx=10)
        ctk.CTkLabel(badge, text=f"v{APP_VERSION} PRO", font=("Orbitron", 11, "bold"), text_color=ACCENT_PRI).pack(side="left", padx=(10, 2), pady=2)
        self.cursor_label = ctk.CTkLabel(badge, text="▋", font=("Courier New", 11, "bold"), text_color=ACCENT_PRI, width=10)
        self.cursor_label.pack(side="left", padx=(0, 5))
        
        status_frame = ctk.CTkFrame(bar, fg_color="transparent")
        status_frame.pack(side="right", padx=20)
        self.status_label = ctk.CTkLabel(status_frame, text="SYSTEM READY", font=("Share Tech Mono", 12, "bold"), text_color=TEXT_SEC)
        self.status_label.pack(side="left", padx=5)
        self.dot_canvas = tk.Canvas(status_frame, width=20, height=20, bg=BG_MAIN, highlightthickness=0)
        self.dot_canvas.pack(side="left")
        self.dot_canvas.create_oval(6, 6, 14, 14, fill=ACCENT_SEC, outline="", tags="dot")
        
        self.top_canvas = ctk.CTkFrame(self.main_container, height=2, fg_color=ACCENT_PRI, corner_radius=0)
        self.top_canvas.pack(fill="x", pady=(5, 5))

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self.main_container,
            fg_color="transparent",
            segmented_button_fg_color=BG_MAIN,
            segmented_button_selected_color=BORDER,
            segmented_button_unselected_color=BG_MAIN,
            segmented_button_selected_hover_color=BG_CARD,
            segmented_button_unselected_hover_color=BG_CARD,
            text_color=ACCENT_PRI,
        )
        self.tabview.pack(fill="both", expand=True, padx=15, pady=5)

        tab_documentary = self.tabview.add("🎬 DOCUMENTARY")
        tab_settings    = self.tabview.add("⚙ SETTINGS")
        tab_history     = self.tabview.add("📋 HISTORY")

        self.doc_queue = queue.Queue()

        self.documentary_tab = DocumentaryTab(tab_documentary, progress_queue=self.doc_queue, app_ref=self)
        self.documentary_tab.pack(fill="both", expand=True)

        self.settings_tab = SettingsTab(tab_settings, app_ref=self)
        self.settings_tab.pack(fill="both", expand=True)

        self.history_tab = HistoryTab(tab_history, app_ref=self)
        self.history_tab.pack(fill="both", expand=True)

    def _build_bottom_bar(self):
        self.bottom_canvas = ctk.CTkFrame(self.main_container, height=2, fg_color=BORDER, corner_radius=0)
        self.bottom_canvas.pack(fill="x", side="bottom")

        bar = ctk.CTkFrame(self.main_container, fg_color=BG_MAIN, height=30, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="NEURAL CORE: HunterIsLive", font=("Share Tech Mono", 11), text_color=TEXT_SEC).pack(side="left", padx=20)
        
        self.backend_label = ctk.CTkLabel(bar, text="", font=("Share Tech Mono", 11), text_color=ACCENT_PRI)
        self.backend_label.pack(side="right", padx=20)
        self.update_backend_labels()
        
    def update_backend_labels(self):
        tts = config.get("tts.backend", "omnivoice").upper()
        self.backend_label.configure(text=f"AUDIO_SUBROUTINE: [{tts}]")

    def set_system_state(self, state: str):
        self.sys_state = state
        self.dot_canvas.delete("dot")
        if state == "READY":
            self.status_label.configure(text="SYSTEM READY", text_color=TEXT_SEC)
            self.dot_canvas.create_oval(6, 6, 14, 14, fill=ACCENT_SEC, outline="", tags="dot")
        elif state == "PROCESSING":
            self.status_label.configure(text="PROCESSING", text_color=ACCENT_WARN)
            self.dot_canvas.create_oval(6, 6, 14, 14, fill=ACCENT_WARN, outline="", tags="dot")
        elif state == "ERROR":
            self.status_label.configure(text="SYSTEM ERROR", text_color=ACCENT_RED)
            self.dot_canvas.create_oval(6, 6, 14, 14, fill=ACCENT_RED, outline="", tags="dot")

if __name__ == "__main__":
    app = GhostCreatorApp()
    app.mainloop()
