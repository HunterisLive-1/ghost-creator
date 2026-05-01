"""
gui/tabs/direct_upload_tab.py — Direct Upload Tab
=================================================
Allows users to select any local video, auto-fill metadata using Gemini,
and upload it via the Ghost Creator uploader.
"""

from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core.config_manager import config
from modules.uploader import upload_to_youtube

BG_MAIN    = "#050A10"
BG_SEC     = "#0A121A"
BG_CARD    = "#0F1A24"
BORDER     = "#1A2B3D"
ACCENT_PRI = "#0088FF"
ACCENT_SEC = "#00BFFF"
ACCENT_DOC = "#A020F0"
ACCENT_GRN = "#00CC66"
ACCENT_RED = "#FF4444"
TEXT_PRI   = "#E6F0FF"
TEXT_SEC   = "#88AADD"
TEXT_HINT  = "#4A6080"


class DirectUploadTab(ctk.CTkFrame):
    def __init__(self, parent, app_ref):
        super().__init__(parent, fg_color=BG_MAIN)
        self.app_ref = app_ref
        self.video_path = None
        self.is_uploading = False
        
        self._build_ui()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_SEC, corner_radius=0, border_width=1, border_color=ACCENT_PRI)
        hdr.pack(fill="x", padx=20, pady=20)
        ctk.CTkLabel(hdr, text="[ 📤 DIRECT UPLOAD — GHOST UPLOADER ]", 
                     font=("Orbitron", 16, "bold"), text_color=ACCENT_PRI).pack(pady=15)
        
        # Select Video
        card_vid = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, border_width=1, border_color=BORDER)
        card_vid.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(card_vid, text="SELECT VIDEO:", font=("Orbitron", 12, "bold"), text_color=TEXT_SEC).pack(anchor="w", padx=15, pady=(10, 5))
        
        row_v = ctk.CTkFrame(card_vid, fg_color="transparent")
        row_v.pack(fill="x", padx=15, pady=(0, 15))
        self.ent_vid = ctk.CTkEntry(row_v, font=("Share Tech Mono", 12), text_color=TEXT_PRI, fg_color=BG_MAIN, border_color=BORDER)
        self.ent_vid.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(row_v, text="BROWSE", width=100, fg_color=ACCENT_PRI, command=self._browse_video).pack(side="left")
        
        # Metadata
        card_meta = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, border_width=1, border_color=BORDER)
        card_meta.pack(fill="x", padx=20, pady=10)
        
        row_mh = ctk.CTkFrame(card_meta, fg_color="transparent")
        row_mh.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(row_mh, text="METADATA:", font=("Orbitron", 12, "bold"), text_color=TEXT_SEC).pack(side="left")
        ctk.CTkButton(row_mh, text="🤖 AI FILL (Gemini)", font=("Share Tech Mono", 11, "bold"), 
                      fg_color="#330044", border_color=ACCENT_DOC, border_width=1, height=28,
                      command=self._do_ai_fill).pack(side="right")
        
        # Title
        ctk.CTkLabel(card_meta, text="Title:").pack(anchor="w", padx=15)
        self.ent_title = ctk.CTkEntry(card_meta, width=600, font=("Share Tech Mono", 12))
        self.ent_title.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Desc
        ctk.CTkLabel(card_meta, text="Description:").pack(anchor="w", padx=15)
        self.txt_desc = ctk.CTkTextbox(card_meta, width=600, height=80, font=("Share Tech Mono", 12))
        self.txt_desc.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Tags
        ctk.CTkLabel(card_meta, text="Tags (comma separated):").pack(anchor="w", padx=15)
        self.ent_tags = ctk.CTkEntry(card_meta, width=600, font=("Share Tech Mono", 12))
        self.ent_tags.pack(anchor="w", padx=15, pady=(0, 10))
        
        # Vis
        ctk.CTkLabel(card_meta, text="Visibility:").pack(anchor="w", padx=15)
        self.vis_menu = ctk.CTkOptionMenu(card_meta, values=["Public", "Unlisted", "Private", "Draft"], width=150)
        self.vis_menu.set("Unlisted")
        self.vis_menu.pack(anchor="w", padx=15, pady=(0, 15))
        
        # Log
        card_log = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, border_width=1, border_color=BORDER)
        card_log.pack(fill="both", expand=True, padx=20, pady=10)
        self.log_box = ctk.CTkTextbox(card_log, font=("Consolas", 11), fg_color="#020608", state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Footer
        ftr = ctk.CTkFrame(self, fg_color="transparent")
        ftr.pack(fill="x", padx=20, pady=10)
        self.btn_upload = ctk.CTkButton(ftr, text="▶ START UPLOAD", font=("Orbitron", 14, "bold"),
                                        fg_color=ACCENT_GRN, hover_color="#009944", text_color="#000000",
                                        command=self._start_upload)
        self.btn_upload.pack(side="left")

    def set_video_for_upload(self, path: str | Path, *, title_hint: str | None = None) -> None:
        """Called from History / Ghost Editor flow to pre-fill the upload form."""
        p = Path(path)
        self.video_path = str(p.resolve()) if p.exists() else str(p)
        self.ent_vid.delete(0, "end")
        self.ent_vid.insert(0, self.video_path)
        if title_hint:
            self.ent_title.delete(0, "end")
            self.ent_title.insert(0, title_hint.strip()[:100])
        elif not self.ent_title.get().strip():
            self.ent_title.delete(0, "end")
            self.ent_title.insert(0, p.stem)

    def _browse_video(self):
        p = filedialog.askopenfilename(title="Select Video to Upload", filetypes=[("Video", "*.mp4 *.mov *.avi *.webm")])
        if p:
            self.set_video_for_upload(p)

    def _do_ai_fill(self):
        if not self.video_path:
            messagebox.showwarning("Error", "Please select a video first!")
            return
            
        def run():
            self._append_log("🤖 Asking Gemini to generate metadata based on filename...")
            try:
                import google.generativeai as genai
                import json
                
                api_key = config.get("api_keys.gemini", "")
                if not api_key:
                    self._append_log("❌ Gemini API key not set in config!")
                    return
                
                genai.configure(api_key=api_key)
                model_name = config.get("gemini_model", "gemini-2.5-flash")
                model = genai.GenerativeModel(model_name)
                
                fname = Path(self.video_path).stem
                prompt = (f"I have a video file named '{fname}'. "
                          f"Generate an engaging YouTube title, a detailed 3-line description, and 10 relevant tags. "
                          f"Respond in pure JSON format: {{\"title\": \"...\", \"description\": \"...\", \"tags\": [\"...\"]}}")
                
                resp = model.generate_content(prompt)
                txt = resp.text.strip()
                if txt.startswith("```json"): txt = txt[7:-3]
                elif txt.startswith("```"): txt = txt[3:-3]
                
                data = json.loads(txt.strip())
                self.after(0, self._apply_metadata, data)
                self._append_log("✅ Metadata filled by AI!")
            except Exception as e:
                self._append_log(f"❌ AI Fill failed: {e}")
                
        threading.Thread(target=run, daemon=True).start()

    def _apply_metadata(self, data):
        self.ent_title.delete(0, "end")
        self.ent_title.insert(0, data.get("title", ""))
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", data.get("description", ""))
        self.ent_tags.delete(0, "end")
        self.ent_tags.insert(0, ", ".join(data.get("tags", [])))

    def _append_log(self, msg):
        def _w():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"> {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _w)

    def _start_upload(self):
        if not self.video_path: return
        if self.is_uploading: return
        
        self.is_uploading = True
        self.btn_upload.configure(state="disabled", text="⏳ UPLOADING...")
        self._append_log("🚀 Starting upload to YouTube Studio...")
        
        meta = {
            "title": self.ent_title.get().strip()[:100],
            "description": self.txt_desc.get("1.0", "end-1c").strip(),
            "tags": [t.strip() for t in self.ent_tags.get().split(",") if t.strip()]
        }
        config.set("pipeline.upload_mode", self.vis_menu.get().lower())
        config.save()
        
        def _prog(msg): self._append_log(msg)
        
        def run():
            try:
                upload_to_youtube(Path(self.video_path), meta, progress_callback=_prog)
                self._append_log("✅ UPLOAD COMPLETE! 🚀")
            except Exception as e:
                self._append_log(f"❌ Upload failed: {e}")
            finally:
                self.after(0, self._reset_btn)
                
        threading.Thread(target=run, daemon=True).start()

    def _reset_btn(self):
        self.is_uploading = False
        self.btn_upload.configure(state="normal", text="▶ START UPLOAD")
