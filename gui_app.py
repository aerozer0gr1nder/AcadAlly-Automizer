import sys
import os
import time
import threading
import importlib.util
from datetime import datetime
import customtkinter as ctk
from PIL import Image
import requests
import io


# Load the automation engine from "acadally_automizer-2.0.py". The filename
# contains characters that are not valid in a Python module name, so it is
# loaded explicitly by path instead of via a normal import statement.
_ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acadally_automizer-2.0.py")
_engine_spec = importlib.util.spec_from_file_location("acadally_automizer_2_0", _ENGINE_PATH)
_acadally_engine = importlib.util.module_from_spec(_engine_spec)
_engine_spec.loader.exec_module(_acadally_engine)
AcadallyBot = _acadally_engine.AcadallyBot

# --- CONFIGURATION ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# --- COLORS ---
BG_COLOR = "#08090D"
PANEL_COLOR = "#0F111A"
ACCENT_CYAN = "#00F0FF"
ACCENT_MAGENTA = "#FF00FF"
ACCENT_PURPLE = "#7000FF"
TEXT_PRIMARY = "#E0E6ED"
TEXT_SECONDARY = "#94A3B8"
SUCCESS_GREEN = "#10B981"
ERROR_RED = "#EF4444"
BORDER_COLOR = "#1C1F2E"

class BotWorker(threading.Thread):
    def __init__(self, api_key, mode, app):
        super().__init__()
        self.api_key = api_key
        self.mode = mode
        self.app = app
        self.bot = None
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()

    def log_callback(self, message, level="INFO"):
        self.app.add_log(message, level)

    def run(self):
        try:
            self.app.update_workflow_step(1)
            self.app.update_status("LAUNCHING CHROME")
            self.bot = AcadallyBot(self.api_key, self.log_callback)
            if not self.bot.setup_driver():
                self.log_callback("Failed to launch browser", "ERROR")
                return

            self.app.update_status("WAITING FOR USER READY")
            self.log_callback("Browser launched. Please login and click 'I'm Ready' in the app.")
            self.app.show_ready_button()
            
            # Wait for user to confirm they are ready
            while not self.ready_event.is_set() and not self.stop_event.is_set():
                time.sleep(0.5)
            
            if self.stop_event.is_set(): return
            
            self.app.hide_ready_button()

            if self.mode == "Single Quiz":
                self.run_single_mode()
            else:
                self.run_batch_mode()

        except Exception as e:
            self.log_callback(f"Critical failure: {e}", "ERROR")
        finally:
            self.app.update_workflow_step(0)
            self.app.on_finished()

    def run_single_mode(self):
        self.app.update_status("WAITING FOR QUIZ")
        self.log_callback("Navigate to your quiz and reach the first question.")
        
        while not self.stop_event.is_set():
            if self.bot.wait_until_on_first_question(timeout_s=2):
                break
            time.sleep(1)
        
        if self.stop_event.is_set(): return
        
        self.app.update_workflow_step(3)
        self.app.update_status("SOLVING QUIZ")
        self.bot.run_quiz_automation(self.stop_event)

    def run_batch_mode(self):
        self.app.update_status("SCANNING QUESTS")
        
        while not self.stop_event.is_set():
            self.app.update_workflow_step(2)
            if self.bot.find_and_click_next_quest_card():
                break
            time.sleep(2)
            
        quizzes_run = 0
        while quizzes_run < 50 and not self.stop_event.is_set():
            if quizzes_run > 0:
                self.app.update_workflow_step(2)
                if not self.bot.find_and_click_next_quest_card():
                    break
            
            while not self.bot.handle_start_or_resume_popup() and not self.stop_event.is_set():
                time.sleep(1)
            
            if self.stop_event.is_set(): break
            
            if not self.bot.wait_until_on_first_question():
                self.bot.wait_for_results_page_and_go_back()
                continue
                
            quizzes_run += 1
            self.app.update_workflow_step(4)
            self.app.update_status(f"SOLVING QUIZ #{quizzes_run}")
            self.bot.run_quiz_automation(self.stop_event)
            
            self.app.update_workflow_step(5)
            self.bot.confirm_submit_popup()
            self.bot.wait_for_results_page_and_go_back()
            
        self.app.update_status("COMPLETED")

class LogWindow(ctk.CTkToplevel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("SYSTEM DIAGNOSTICS")
        self.geometry("800x500")
        self.configure(fg_color=BG_COLOR)
        
        self.log_area = ctk.CTkTextbox(self, font=("Consolas", 12), text_color="#A5B4FC")
        self.log_area.pack(fill="both", expand=True, padx=20, pady=20)
        self.log_area.configure(state="disabled")

    def add_log(self, message, level):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_area.configure(state="normal")
        self.log_area.insert("end", f"[{ts}] [{level}] {message}\n")
        self.log_area.configure(state="disabled")
        self.log_area.see("end")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("QUIZ // CORE")
        self.geometry("1100x750")
        self.configure(fg_color=BG_COLOR)
        
        self.worker = None
        self.log_window = None
        
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.init_sidebar()
        self.init_main()
        
    def init_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=BG_COLOR, border_width=1, border_color=PANEL_COLOR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(5, weight=1)
        
        logo_label = ctk.CTkLabel(self.sidebar, text="QUIZ//CORE", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_CYAN)
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 40))
        
        self.btn_dash = ctk.CTkButton(self.sidebar, text="🏠  Dashboard", anchor="w", fg_color="transparent", text_color=TEXT_SECONDARY, hover_color=PANEL_COLOR, command=self.show_dashboard)
        self.btn_dash.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_logs = ctk.CTkButton(self.sidebar, text="📜  Logs", anchor="w", fg_color="transparent", text_color=TEXT_SECONDARY, hover_color=PANEL_COLOR, command=self.show_logs)
        self.btn_logs.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        self.btn_settings = ctk.CTkButton(self.sidebar, text="⚙️  Settings", anchor="w", fg_color="transparent", text_color=TEXT_SECONDARY, hover_color=PANEL_COLOR, command=self.show_settings)
        self.btn_settings.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        branding = ctk.CTkLabel(self.sidebar, text="AUTOMATE\nLEARN\nACHIEVE", font=ctk.CTkFont(size=11), text_color="#1E293B", justify="left")
        branding.grid(row=6, column=0, padx=20, pady=20)

    def init_main(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=25, pady=20)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # Header
        header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        self.status_btn = ctk.CTkButton(header, text="● SYSTEM READY", font=ctk.CTkFont(size=11), fg_color="transparent", border_width=1, border_color=SUCCESS_GREEN, text_color=SUCCESS_GREEN, height=24)
        self.status_btn.pack(side="left")

        # Image
        response_operations=requests.get("https://imgh.in/host/h2qa08")
        response_nvidia=requests.get("https://imgh.in/host/x5476f")
        response_chrome = requests.get("https://imgh.in/host/inod6o")
        button_image = ctk.CTkImage(
        light_image=Image.open(io.BytesIO(response_chrome.content)), # Image for light mode
        size=(26, 26)                                # Desired display size (width, height)
        )
        nvidia_img=ctk.CTkImage(
        light_image=Image.open(io.BytesIO(response_nvidia.content)), # Image for light mode
        size=(128,78)                                # Desired display size (width, height)
        )
        operations_img=ctk.CTkImage(
            light_image=Image.open(io.BytesIO(response_operations.content)),
            size=(128,125)
        )
    
   
        # Control Panel
        self.ctrl_panel = ctk.CTkFrame(self.main_container, fg_color=PANEL_COLOR, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        self.ctrl_panel.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        
        title = ctk.CTkLabel(self.ctrl_panel, text="Quiz Control Center", font=ctk.CTkFont(size=48, family="Kristen ITC", weight="bold"), text_color=ACCENT_CYAN, anchor="center")
        title.pack(padx=30, pady=(30, 5), anchor="w")
        
        sub = ctk.CTkLabel(self.ctrl_panel, text="Automated quiz solving • Smart study • Better results",font=ctk.CTkFont(size=16,family="Ink Free"), text_color=TEXT_SECONDARY)
        sub.pack(padx=30, pady=(0, 30), anchor="w")
        
        btn_row = ctk.CTkFrame(self.ctrl_panel, fg_color="transparent")
        btn_row.pack(padx=30, pady=(0, 30), fill="x")
        
        self.launch_btn = ctk.CTkButton(btn_row, image=button_image, text="▶ LAUNCH CHROME & START", font=ctk.CTkFont(size=16, family="Lucida Handwriting", weight="bold"), height=50, corner_radius=25, fg_color=ACCENT_PURPLE, hover_color=ACCENT_MAGENTA, command=self.toggle_automation)
        self.launch_btn.pack(side="left")

        self.ready_btn = ctk.CTkButton(btn_row, text="✅ I'M LOGGED IN & READY", font=ctk.CTkFont(size=16, family="Lucida Handwriting", weight="bold"), height=50, corner_radius=25, fg_color=SUCCESS_GREEN, hover_color="#059669", command=self.mark_user_ready)
        self.ready_btn.pack(side="left", padx=20)
        self.ready_btn.pack_forget() # Hide initially
        
        # Middle Section
        mid_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        mid_row.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        mid_row.grid_columnconfigure(0, weight=2)
        mid_row.grid_columnconfigure(1, weight=1)
        
        wf_card = ctk.CTkFrame(mid_row, fg_color=PANEL_COLOR, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        wf_card.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        
        wf_title = ctk.CTkLabel(wf_card, text="WORKFLOW STATUS", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_SECONDARY)
        wf_title.pack(padx=20, pady=15, anchor="w")
        
        self.node_frame = ctk.CTkFrame(wf_card, fg_color="transparent")
        self.node_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        self.nodes = []
        for i, (icon, label) in enumerate([("⏻", "Idle"), ("🌐", "Launch"), ("📋", "Quest"), ("❓", "Select"), ("✎", "Solve"), ("✓", "Submit")]):
            node = ctk.CTkLabel(self.node_frame, text=f"{icon}\n{label}", font=ctk.CTkFont(size=14), text_color="#334155")
            node.pack(side="left", expand=True)
            self.nodes.append(node)
        self.nodes[0].configure(text_color=ACCENT_CYAN)
        
        info_card = ctk.CTkFrame(mid_row, fg_color=PANEL_COLOR, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        info_card.grid(row=0, column=1, sticky="nsew")
        
        info_title = ctk.CTkLabel(info_card, text="QUICK INFO", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_SECONDARY)
        info_title.pack(padx=20, pady=15, anchor="w")
        
        self.info_text = ctk.CTkLabel(info_card, text="Browser: Chrome\nMode: Auto\nStatus: Ready\nVersion: 3.0", justify="left", text_color=ACCENT_CYAN)
        self.info_text.pack(padx=20, pady=(0, 20), anchor="w")
        
        # Bottom Section
        bottom_row = ctk.CTkFrame(self.main_container, fg_color="transparent")
        bottom_row.grid(row=3, column=0, sticky="nsew")
        bottom_row.grid_columnconfigure(0, weight=1)
        bottom_row.grid_columnconfigure(1, weight=2)
        
        prog_card = ctk.CTkFrame(bottom_row, fg_color=PANEL_COLOR, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        prog_card.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        
        prog_title = ctk.CTkLabel(prog_card, text="PROGRESS", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_SECONDARY)
        prog_title.pack(padx=20, pady=15, anchor="w")
        
        self.prog_val = ctk.CTkLabel(prog_card, text="0%", font=ctk.CTkFont(size=40, weight="bold"), text_color=ACCENT_CYAN)
        self.prog_val.pack(padx=20, pady=(0, 20))
        
        log_card = ctk.CTkFrame(bottom_row, fg_color=PANEL_COLOR, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        log_card.grid(row=0, column=1, sticky="nsew")
        
        log_title = ctk.CTkLabel(log_card, text="LOGS (PREVIEW)", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_SECONDARY)
        log_title.pack(padx=20, pady=15, anchor="w")
        
        self.log_preview = ctk.CTkTextbox(log_card, height=120, font=("Consolas", 10), text_color="#A5B4FC", fg_color="#050608")
        self.log_preview.pack(fill="both", padx=20, pady=(0, 20))
        self.log_preview.configure(state="disabled")

        # Settings Overlay
        self.settings_frame = ctk.CTkFrame(self, fg_color=BG_COLOR, corner_radius=0, border_width=1, border_color=PANEL_COLOR)
        self.settings_frame.place(relx=0.2, rely=0, relwidth=0.8, relheight=1)
        self.settings_frame.place_forget()
        
        set_title = ctk.CTkLabel(self.settings_frame, text="CONFIGURATION", font=ctk.CTkFont(size=20, weight="bold"))
        set_title.pack(padx=50, pady=(50, 30), anchor="w")
        
        ctk.CTkLabel(self.settings_frame,image=nvidia_img, compound="left", text="NVIDIA API KEY", font=("Comic Sans MS",16,"bold")).pack(padx=50, pady=(0, 5), anchor="w")
        self.api_input = ctk.CTkEntry(self.settings_frame, width=400, show="*")
        self.api_input.pack(padx=50, pady=(0, 20), anchor="w")
        
        ctk.CTkLabel(self.settings_frame,image=operations_img, compound="left", text="OPERATION MODE", font=("Comic Sans MS",16,"bold")).pack(padx=50, pady=(0, 5), anchor="w")
        self.mode_combo = ctk.CTkComboBox(self.settings_frame, values=["Single Quiz", "All Quizzes (Batch)"], width=400)
        self.mode_combo.pack(padx=50, pady=(0, 40), anchor="w")
        
        # Restore previously saved settings, if any.
        saved_key, saved_mode = _acadally_engine.load_settings()
        if saved_key:
            self.api_input.delete(0, "end")
            self.api_input.insert(0, saved_key)
        if saved_mode in self.mode_combo.cget("values"):
            self.mode_combo.set(saved_mode)
        
        ctk.CTkButton(self.settings_frame, text="SAVE & CLOSE", command=self.save_settings).pack(padx=50, pady=20, anchor="w")

    def save_settings(self):
        api_key = self.api_input.get().strip()
        mode = self.mode_combo.get()
        try:
            _acadally_engine.save_settings(api_key, mode)
            self.add_log("Settings saved (API key + operation mode).", "INFO")
        except Exception as e:
            self.add_log(f"Failed to save settings: {e}", "ERROR")
        self.show_dashboard()

    def show_dashboard(self):
        self.settings_frame.place_forget()
        self.btn_dash.configure(fg_color=PANEL_COLOR, text_color=ACCENT_CYAN)
        self.btn_settings.configure(fg_color="transparent", text_color=TEXT_SECONDARY)

    def show_settings(self):
        self.settings_frame.place(relx=0.2, rely=0, relwidth=0.8, relheight=1)
        self.btn_settings.configure(fg_color=PANEL_COLOR, text_color=ACCENT_CYAN)
        self.btn_dash.configure(fg_color="transparent", text_color=TEXT_SECONDARY)

    def show_logs(self):
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = LogWindow(self)
        else:
            self.log_window.focus()

    def show_ready_button(self):
        self.after(0, lambda: self.ready_btn.pack(side="left", padx=20))

    def hide_ready_button(self):
        self.after(0, self.ready_btn.pack_forget)

    def mark_user_ready(self):
        if self.worker and self.worker.is_alive():
            self.worker.ready_event.set()
            self.add_log("User confirmed readiness.", "INFO")

    def add_log(self, message, level):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_preview.configure(state="normal")
        self.log_preview.insert("end", f"[{ts}] [{level}] {message}\n")
        self.log_preview.configure(state="disabled")
        self.log_preview.see("end")
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.add_log(message, level)

    def update_status(self, text):
        self.status_btn.configure(text=f"● {text}", text_color=ACCENT_CYAN, border_color=ACCENT_CYAN)

    def update_workflow_step(self, step_idx):
        for i, node in enumerate(self.nodes):
            node.configure(text_color=ACCENT_CYAN if i == step_idx else "#334155")

    def toggle_automation(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop_event.set()
            self.launch_btn.configure(text="▶ LAUNCH CHROME & START")
            return

        api_key = self.api_input.get().strip()
        mode = self.mode_combo.get()
        
        self.worker = BotWorker(api_key, mode, self)
        self.launch_btn.configure(text="■ STOP AUTOMATION", font=ctk.CTkFont(size=16, family="Lucida Handwriting", weight="bold"))
        self.worker.start()

    def on_finished(self):
        self.launch_btn.configure(text="▶ LAUNCH CHROME & START", font=ctk.CTkFont(size=16, family="Lucida Handwriting", weight="bold"))
        self.status_btn.configure(text="● SYSTEM READY", text_color=SUCCESS_GREEN, border_color=SUCCESS_GREEN)
        self.hide_ready_button()
        self.update_workflow_step(0)

if __name__ == "__main__":
    app = App()
    app.mainloop()
