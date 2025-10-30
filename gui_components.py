import wx
import sys
import keyboard 
import threading

# Focus library (Windows only)
try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

# --- 1. Standard Output/Error Redirection Class ---
class RedirectText(object):
    """Redirects print/stderr output to a wx.TextCtrl"""
    def __init__(self, aWxTextCtrl):
        self.out = aWxTextCtrl
    def write(self, string):
        if self.out:
            # Safely append text from a non-main thread
            wx.CallAfter(self.out.AppendText, string)
            # Safely scroll to the end
            wx.CallAfter(self.out.ShowPosition, self.out.GetLastPosition()) 
    def flush(self):
        pass

# --- 2. Global Hotkey Listener Class ---
class GlobalHotkeyListener:
    """Detects F1, F2 key presses regardless of program focus"""
    def __init__(self, start_callback, stop_callback):
        self.start_callback = start_callback
        self.stop_callback = stop_callback
        self.running = False
        
    def start(self):
        if self.running: return
        try:
            # Bind F1 to start and F2 to stop, suppressing the default key action
            keyboard.add_hotkey('f1', self._on_f1_press, suppress=True) 
            keyboard.add_hotkey('f2', self._on_f2_press, suppress=True)
            self.running = True
        except Exception as e:
            # print("Warning: Hotkey registration failed. Try running as administrator:", e)
            pass

    def stop(self):
        if not self.running: return
        try:
            keyboard.remove_hotkey('f1')
            keyboard.remove_hotkey('f2')
        except KeyError:
            pass
        self.running = False

    def _on_f1_press(self):
        if self.start_callback:
            # Use wx.CallAfter to execute the UI update safely
            wx.CallAfter(self.start_callback)

    def _on_f2_press(self):
        if self.stop_callback:
            # Use wx.CallAfter to execute the UI update safely
            wx.CallAfter(self.stop_callback)

# --- 3. Fishing Region Selection Overlay ---
class RegionSelector(wx.Frame):
    def __init__(self, parent):
        # Create a transparent, always-on-top window without a taskbar icon
        super(RegionSelector, self).__init__(parent, style=wx.FRAME_NO_TASKBAR | wx.STAY_ON_TOP | wx.FULL_REPAINT_ON_RESIZE)
        self.parent_frame = parent
        self.SetCursor(wx.Cursor(wx.CURSOR_CROSS)) 
        self.SetTransparent(180) # 180 out of 255 transparency
        self.SetBackgroundColour(wx.BLACK) 
        
        self.start_pos = None
        self.end_pos = None
        
        # Set the size to cover the entire screen
        screen_size = wx.GetDisplaySize()
        self.SetSize(screen_size)
        self.SetPosition((0, 0))
        
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.Bind(wx.EVT_MOTION, self.on_mouse_move)
        self.Bind(wx.EVT_LEFT_UP, self.on_left_up)
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.on_erase_background) # Prevent flicker
        self.Bind(wx.EVT_PAINT, self.on_paint)
        
        self.Show()
        self.Maximize()
        self.CaptureMouse()

    def on_left_down(self, event):
        # Start selection
        self.start_pos = event.GetPosition()
        self.end_pos = None 
        self.Refresh()

    def on_mouse_move(self, event):
        # Draw rectangle while dragging
        if self.start_pos and event.Dragging():
            self.end_pos = event.GetPosition()
            self.Refresh()

    def on_left_up(self, event):
        # Selection complete
        if self.start_pos and self.end_pos:
            x1 = min(self.start_pos.x, self.end_pos.x)
            y1 = min(self.start_pos.y, self.end_pos.y)
            x2 = max(self.start_pos.x, self.end_pos.x)
            y2 = max(self.start_pos.y, self.end_pos.y)
            
            # Call the parent's handler with the region tuple (x, y, width, height)
            wx.CallAfter(self.parent_frame.on_region_selected, (x1, y1, x2 - x1, y2 - y1))

        self.ReleaseMouse()
        self.Destroy()

    def on_paint(self, event):
        # Draw the selection rectangle
        dc = wx.PaintDC(self)
        pen = wx.Pen(wx.Colour(255, 255, 0), 2) # Yellow border
        dc.SetPen(pen)
        dc.SetBrush(wx.Brush(wx.BLUE, wx.BRUSHSTYLE_TRANSPARENT)) # Transparent fill
        
        if self.start_pos and self.end_pos:
            x1 = min(self.start_pos.x, self.end_pos.x)
            y1 = min(self.start_pos.y, self.end_pos.y)
            x2 = max(self.start_pos.x, self.end_pos.x)
            y2 = max(self.start_pos.y, self.end_pos.y)
            dc.DrawRectangle(x1, y1, x2 - x1, y2 - y1)

    def on_erase_background(self, event):
        # Do nothing to prevent flickering
        pass 
