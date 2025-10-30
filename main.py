import wx
import sys
import threading
import os # os 모듈 추가
from PIL import Image
import time
import io 
import numpy as np
import cv2 

# --- Resource Path Utility (Crucial for PyInstaller) ---
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
# --- End of Resource Path Utility ---

# --- Import 3D Fish Logo Module ---
try:
    from fish import FishGLCanvas
except ImportError:
    print("Error: fish_logo_3d.py not found. Please ensure it is in the same directory.")
    sys.exit(1)
# --- End of Fish Logo Import ---

# Separated module import (gui_components.py and fishing_bot_core.py must be in the same directory)
try:
    from gui_components import RedirectText, GlobalHotkeyListener, RegionSelector
    from fishing_bot_core import FishingBotCore
except ImportError:
    # Log in English as per previous instruction
    print("Error: gui_components.py or fishing_bot_core.py file is missing or not in the path.")
    sys.exit(1)


class FishingBotFrame(wx.Frame):
    
    def __init__(self, parent, title):
        # 1. Window title set to IOSTREAM
        super(FishingBotFrame, self).__init__(parent, title='IOSTREAM', size=(300, 650)) 
        self.SetMinSize(wx.Size(300, 650))
        
        # --- NEW: Set Window Icon ---
        self.set_window_icon()
        # -----------------------------
        
        # 2. STYLE: Windows 98 Gray background color
        win98_gray = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
        self.SetBackgroundColour(win98_gray)
        
        self.casting_area_ref = {"area": None} 
        
        self.log_text = None 
        self.debug_img_bitmap = None
        self.DEBUG_IMG_SIZE = (150, 150) 

        self.bot_core = FishingBotCore(
            casting_area_ref=self.casting_area_ref,
            log_callback=self._log_message,
            debug_img_callback=self._update_debug_image 
        )
        
        # --- GUI Setup Start ---
        panel = wx.Panel(self)
        panel.SetBackgroundColour(win98_gray) # Apply gray background to the panel
        main_vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.notebook = wx.Notebook(panel)
        self.notebook.SetBackgroundColour(win98_gray) # Apply gray background to notebook tabs
        
        # Add Control/Log tab first
        self.control_panel = wx.Panel(self.notebook)
        self.control_panel.SetBackgroundColour(win98_gray) 
        self._setup_control_tab() 
        self.notebook.AddPage(self.control_panel, "▶️ Control & Log")
        
        self.settings_panel = wx.Panel(self.notebook)
        self.settings_panel.SetBackgroundColour(win98_gray) 
        self._setup_settings_tab() 
        self.notebook.AddPage(self.settings_panel, "⚙️ Settings")
        
        main_vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(main_vbox) 
        panel.Layout() 
        
        self.Centre()
        self.Show()
        
        # Redirect sys.stdout/stderr after the log TextCtrl is created
        sys.stdout = RedirectText(self.log_text)
        sys.stderr = RedirectText(self.log_text)
        
        self.hotkey_listener = GlobalHotkeyListener(
            start_callback=self.on_start_bot,
            stop_callback=self.on_stop_bot
        )
        self.hotkey_listener.start()
        
        self._log_message(f"--- Fishing Bot GUI Initialized (Template Matching Applied) ---")
        self._log_message("💡 Before starting the bot, please set the fishing area and time in the [⚙️ Settings] tab.")
        
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def set_window_icon(self):
        """Sets the window icon using the resource_path utility."""
        ICON_FILE_PATH = "fish.ico"
        icon_abs_path = resource_path(ICON_FILE_PATH)
        
        if not os.path.exists(icon_abs_path):
            print(f"⚠️ Warning: Icon file '{ICON_FILE_PATH}' not found at {icon_abs_path}. Using default icon.")
            return

        try:
            icon = wx.Icon(icon_abs_path, wx.BITMAP_TYPE_ICO)
            self.SetIcon(icon)
        except Exception as e:
            print(f"❌ Error setting icon from '{ICON_FILE_PATH}': {e}")
            
    # --- Log and Image Update Methods ---
    def _log_message(self, message):
        """Outputs messages received from BotCore to the GUI log (thread safe)"""
        if self.log_text and self.log_text.IsShown():
            wx.CallAfter(self._append_log_text, message)
    
    def _append_log_text(self, message):
        timestamp = time.strftime("[%H:%M:%S] ")
        self.log_text.AppendText(timestamp + message + "\n")
        self.log_text.ShowPosition(self.log_text.GetLastPosition())

    def _update_debug_image(self, pil_image: Image):
        """Displays the PIL Image passed from BotCore on wxStaticBitmap. (thread safe)"""
        wx.CallAfter(self._apply_debug_image_to_wx, pil_image)

    def _apply_debug_image_to_wx(self, pil_image: Image):
        """Applies the PIL image to wxStaticBitmap on the main thread"""
        try:
            # STYLE: Use a simple, smaller font for better retro look
            font = self.debug_img_label.GetFont()
            font.SetPointSize(9) 
            self.debug_img_label.SetFont(font)
            
            resized_img = pil_image.resize(self.DEBUG_IMG_SIZE, Image.LANCZOS)
            wx_image = wx.Image(resized_img.width, resized_img.height)
            wx_image.SetData(resized_img.convert("RGB").tobytes()) 

            self.debug_img_bitmap = wx.Bitmap(wx_image)
            self.debug_img_label.SetBitmap(self.debug_img_bitmap)
            
            self.control_panel.Layout()
            
        except Exception as e:
            self._log_message(f"❌ Debug image display error: {e}")

    # --- Window/Bot Control Methods ---
    def on_close(self, event):
        """Handles window close event"""
        self.bot_core.stop_bot()
        self.hotkey_listener.stop() 
        
        if self.bot_core.fishing_thread and self.bot_core.fishing_thread.is_alive():
            self.bot_core.fishing_thread.join(timeout=1.0) 
        self.Destroy()

    def on_start_setting_area(self, event):
        self._log_message("⏳ Starting screen area selection mode...")
        self.Disable() 
        RegionSelector(self)

    def on_region_selected(self, rect_tuple):
        self.Enable()
        x, y, w, h = rect_tuple
        if w > 0 and h > 0:
            self.casting_area_ref["area"] = (x, y, w, h)
            area_str = f"X: {x}, Y: {y}, W: {w}, H: {h}"
            self.area_display.SetLabel(area_str)
            self._log_message(f"✅ Fishing area set: {area_str}.")
            wx.CallAfter(self.capture_and_display_preview, x, y, w, h) 
        else:
            self.casting_area_ref["area"] = None
            self.area_display.SetLabel("Unset (X:-, Y:-, W:-, H:-)")
            self._log_message("⚠️ Fishing area setting cancelled.")
            self.set_default_preview_image(self.preview_bitmap, 280, 140)

    def on_start_bot(self, event=None):
        """Bot Start button/hotkey"""
        if self.bot_core.is_running.is_set():
            self._log_message("⚠️ Bot is already running.")
            return

        try:
            min_t = float(self.min_time_ctrl.GetValue())
            max_t = float(self.max_time_ctrl.GetValue())
            self.bot_core.set_cast_time(min_t, max_t)
        except ValueError:
            self._log_message("🛑 Error: Please enter a valid number for the cast time.")
            return

        self.start_button.Disable()
        self.stop_button.Enable()
        
        self.bot_core.start_bot()
        threading.Timer(0.1, self._check_bot_thread).start()

    def on_stop_bot(self, event=None):
        """Bot Stop button/hotkey"""
        self.bot_core.stop_bot()

    def _check_bot_thread(self):
        """Checks if the bot thread has finished and updates the GUI state"""
        if not self.bot_core.is_running.is_set() and self.bot_core.fishing_thread and not self.bot_core.fishing_thread.is_alive():
            wx.CallAfter(self._on_bot_routine_finished)
        else:
            threading.Timer(0.5, self._check_bot_thread).start()
            
    def _on_bot_routine_finished(self):
        """Clean up GUI after bot loop finishes"""
        self.start_button.Enable()
        self.stop_button.Disable()

    # --- UI/Area Setup Functions ---
    def _setup_settings_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        # STYLE: Use smaller, standard font
        standard_font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)

        # ----------------------------------------
        # NEW: 3D Fish Logo Canvas (NO STATIC BOX BORDER)
        # ----------------------------------------
        FISH_GL_SIZE = (200, 150)
        if 'FishGLCanvas' in globals():
            self.fish_canvas = FishGLCanvas(self.settings_panel, size=FISH_GL_SIZE)
            
            canvas_hbox = wx.BoxSizer(wx.HORIZONTAL)
            canvas_hbox.AddStretchSpacer(1)
            canvas_hbox.Add(self.fish_canvas, 0, wx.ALL | wx.FIXED_MINSIZE, 5) 
            canvas_hbox.AddStretchSpacer(1)
            vbox.Add(canvas_hbox, 0, wx.EXPAND | wx.ALL, 5)
        # ----------------------------------------

        # Simplified label
        area_group = wx.StaticBoxSizer(wx.VERTICAL, self.settings_panel, label="Fishing Area Settings (Detection Area)")
        
        coord_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # FIX: Create StaticText without 'font' keyword, then apply font
        coord_text = wx.StaticText(self.settings_panel, label="Coordinates: ")
        coord_text.SetFont(standard_font)
        coord_hbox.Add(coord_text, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.area_display = wx.StaticText(self.settings_panel, label="Unset (X:-, Y:-, W:-, H:-)") 
        # Apply bold font and smaller size for emphasis
        font = self.area_display.GetFont()
        font.SetPointSize(9) 
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.area_display.SetFont(font)

        coord_hbox.Add(self.area_display, 1, wx.EXPAND) 
        
        # Use default system button style for retro look
        set_area_button = wx.Button(self.settings_panel, label="🎯 Start Area Selection (Screen Drag)")
        set_area_button.Bind(wx.EVT_BUTTON, self.on_start_setting_area) # Ensure binding is present
        
        # Adjust preview image size (to fit GUI size)
        self.preview_bitmap = wx.StaticBitmap(self.settings_panel, size=(280, 140)) # Fits 300px width
        self.set_default_preview_image(self.preview_bitmap, 280, 140)
        
        area_group.Add(coord_hbox, 0, wx.EXPAND | wx.ALL, 5)
        area_group.Add(set_area_button, 0, wx.EXPAND | wx.ALL, 10) 
        
        preview_hbox = wx.BoxSizer(wx.HORIZONTAL)
        preview_hbox.AddStretchSpacer(1)
        preview_hbox.Add(self.preview_bitmap, 0, wx.TOP | wx.BOTTOM, 10) 
        preview_hbox.AddStretchSpacer(1)
        area_group.Add(preview_hbox, 1, wx.EXPAND)
        
        # Simplified label
        time_group = wx.StaticBoxSizer(wx.HORIZONTAL, self.settings_panel, label="Cast Hold Time Setting (seconds)")
        
        # FIX: Min label
        min_label = wx.StaticText(self.settings_panel, label="Min: ")
        min_label.SetFont(standard_font)
        time_group.Add(min_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        
        self.min_time_ctrl = wx.TextCtrl(self.settings_panel, value=str(self.bot_core.min_cast_time), size=(60, -1), style=wx.TE_RIGHT | wx.BORDER_SUNKEN) # Sunken border
        time_group.Add(self.min_time_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        # FIX: Max label
        max_label = wx.StaticText(self.settings_panel, label="Max: ")
        max_label.SetFont(standard_font)
        time_group.Add(max_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)

        self.max_time_ctrl = wx.TextCtrl(self.settings_panel, value=str(self.bot_core.max_cast_time), size=(60, -1), style=wx.TE_RIGHT | wx.BORDER_SUNKEN) # Sunken border
        time_group.Add(self.max_time_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        vbox.Add(area_group, 0, wx.EXPAND | wx.ALL, 10)
        vbox.Add(time_group, 0, wx.EXPAND | wx.ALL, 10)
        vbox.AddStretchSpacer(1)
        self.settings_panel.SetSizer(vbox)


    def _setup_control_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Simplified label
        debug_group = wx.StaticBoxSizer(wx.VERTICAL, self.control_panel, label="Bobber Detection Real-time Debug")
        
        self.debug_img_label = wx.StaticBitmap(self.control_panel, size=self.DEBUG_IMG_SIZE)
        self.set_default_preview_image(self.debug_img_label, self.DEBUG_IMG_SIZE[0], self.DEBUG_IMG_SIZE[1], "Detection Area (150x150)", text_color=wx.Colour(100, 100, 100))
        
        debug_hbox = wx.BoxSizer(wx.HORIZONTAL)
        debug_hbox.AddStretchSpacer(1)
        debug_hbox.Add(self.debug_img_label, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 5)
        debug_hbox.AddStretchSpacer(1)
        debug_group.Add(debug_hbox, 0, wx.EXPAND | wx.ALL, 5)
        
        # Simplified label
        control_group = wx.StaticBoxSizer(wx.VERTICAL, self.control_panel, label="Bot Control") 
        bot_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # STYLE: Removed custom colors and bold font for retro look
        self.start_button = wx.Button(self.control_panel, label="▶️ START (F1)")
        self.stop_button = wx.Button(self.control_panel, label="⏹️ STOP (F2)")
        
        # Apply standard, small font to buttons
        standard_font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.start_button.SetFont(standard_font)
        self.stop_button.SetFont(standard_font)

        # Remove explicit color settings to use OS default (Win98 gray look)
        self.start_button.SetBackgroundColour(wx.NullColour)
        self.stop_button.SetBackgroundColour(wx.NullColour)

        self.start_button.Bind(wx.EVT_BUTTON, self.on_start_bot)
        self.stop_button.Bind(wx.EVT_BUTTON, self.on_stop_bot)
        self.stop_button.Disable()
        
        bot_hbox.Add(self.start_button, 1, wx.EXPAND | wx.RIGHT, 5)
        bot_hbox.Add(self.stop_button, 1, wx.EXPAND | wx.LEFT, 5)
        control_group.Add(bot_hbox, 0, wx.EXPAND | wx.ALL, 5)
        
        # Simplified label
        log_group = wx.StaticBoxSizer(wx.VERTICAL, self.control_panel, label="Bot Activity Log")
        # STYLE: Use BORDER_SUNKEN for classic Windows recessed look
        self.log_text = wx.TextCtrl(self.control_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_SUNKEN)
        # STYLE: Classic white log background
        self.log_text.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)) 
        
        log_group.Add(self.log_text, 1, wx.EXPAND | wx.ALL, 5)
        
        vbox.Add(debug_group, 0, wx.EXPAND | wx.ALL, 10)
        vbox.Add(control_group, 0, wx.EXPAND | wx.ALL, 10)
        vbox.Add(log_group, 1, wx.EXPAND | wx.ALL, 10)
        self.control_panel.SetSizer(vbox)
    
    # --- Helper Methods for Image/Preview ---
    def set_default_preview_image(self, static_bitmap, width, height, text="Selected Area Preview", text_color=wx.BLACK):
        # STYLE: Smaller, standard font for placeholder
        font = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        
        # STYLE: White background for the placeholder area
        placeholder_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        bmp = wx.Bitmap(width, height)
        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(placeholder_bg))
        dc.Clear()
        dc.SetFont(font)
        dc.SetTextForeground(text_color)
        text_w, text_h = dc.GetTextExtent(text)
        dc.DrawText(text, (bmp.GetWidth() - text_w) // 2, (bmp.GetHeight() - text_h) // 2)
        dc.SelectObject(wx.NullBitmap)
        static_bitmap.SetBitmap(bmp)
    
    def capture_and_display_preview(self, x, y, width, height):
        try:
            monitor = {"top": y, "left": x, "width": width, "height": height}
            # The bot_core.sct must be initialized (it is in FishingBotCore)
            sct_img = self.bot_core.sct.grab(monitor) 
            
            # Capture data -> PIL Image conversion (stabilization)
            img_array = np.array(sct_img, dtype=np.uint8)
            img_array_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGRA2RGB)
            pil_img = Image.fromarray(img_array_rgb)
            
            preview_width, preview_height = 280, 140 # Adjusted to fit GUI size
            ratio = min(preview_width / pil_img.width, preview_height / pil_img.height)
            new_width = int(pil_img.width * ratio)
            new_height = int(pil_img.height * ratio)
            
            bmp = wx.Bitmap(preview_width, preview_height)
            dc = wx.MemoryDC(bmp)
            # STYLE: White background for preview area
            dc.SetBackground(wx.Brush(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)))
            dc.Clear()
            
            pil_img = pil_img.resize((new_width, new_height), Image.LANCZOS)
            
            wx_img = wx.Image(pil_img.width, pil_img.height)
            wx_img.SetData(pil_img.convert("RGB").tobytes()) 

            x_offset = (preview_width - new_width) // 2
            y_offset = (preview_height - new_height) // 2
            dc.DrawBitmap(wx.Bitmap(wx_img), x_offset, y_offset)
            dc.SelectObject(wx.NullBitmap)
            self.preview_bitmap.SetBitmap(bmp)
            self.settings_panel.Layout()
        except Exception as e:
            self._log_message(f"❌ Preview capture error: {e}") 


# --- 4. Program Execution ---
if __name__ == '__main__':
    app = wx.App(False) 
    # FIX: Ensure the execution line uses the desired title for clarity
    frame = FishingBotFrame(None, title='IOSTREAM') 
    app.MainLoop() 
