import time
import random
import threading
import pyautogui
import mss
from PIL import Image, ImageDraw
import traceback
import cv2
import numpy as np
import os
import sys

# Focusing library (Windows only)
try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

# PyAutoGUI Fail-safe setting
pyautogui.FAILSAFE = True

class FishingBotCore:
    """Handles all core logic for the fishing bot (detection, actions, loop, minigame)"""

    # --- 🎣 Constants ---
    # 🚨 POSITION_DIFF_THRESHOLD: Minimum vertical drop pixel distance to consider a bite
    POSITION_DIFF_THRESHOLD = 6
    
    MATCH_THRESHOLD = 0.4                  # Template matching accuracy (general bobber)
    
    # Template filenames
    TEMPLATE_FILENAME = "bobber_template.png"              # Template for the bobber floating on water
    MINIGAME_BAR_TEMPLATE_FILENAME = "minigame_bar_template.png" # Template for the entire minigame bar
    
    # Minigame timeout (set to 1 minute)
    MINIGAME_TIMEOUT = 120
    
    # Minigame constants (based on blog logic)
    ROLL_LIMIT = 400                       # RGB sum threshold (standard for bright area detection)
    
    # Minigame bar capture area settings
    MINIGAME_SCAN_WIDTH = 260          # Scan width (260px)
    MINIGAME_SCAN_Y_OFFSET = 15        # Scan start Y position from bar top (0)
    MINIGAME_REEL_STOP_X = 180         # X coordinate within the scan area (0~259) to stop reeling
    
    # Minigame bar detection retry constants
    MAX_BAR_SEARCH_ATTEMPTS = 5        # Maximum retry attempts
    BAR_SEARCH_INTERVAL = 0.3          # Retry interval (seconds)
    
    BOBBER_SEARCH_RADIUS = 30

    # --- Bot State Variables ---
    def __init__(self, casting_area_ref, log_callback=None, debug_img_callback=None, game_window_title="Albion Online Client"):
        self.casting_area_ref = casting_area_ref
        self.log = log_callback if log_callback else print
        self.debug_img_callback = debug_img_callback if debug_img_callback else lambda x: None
        self.GAME_WINDOW_TITLE = game_window_title
        
        # --- Template Loading ---
        self.bobber_template = self._load_template(self.TEMPLATE_FILENAME)
        self.minigame_bar_template = self._load_template(self.MINIGAME_BAR_TEMPLATE_FILENAME)

        # --- State Management ---
        self.is_running = threading.Event()
        self.fishing_thread = None
        self.sct = mss.mss() # Instance for bite detection (used close to the main thread)
        self.is_bite_detected = threading.Event()
        self.previous_bobber_image = None
        
        # 🚨 Add variable to store initial bobber Y coordinate (for vertical drop measurement)
        self.initial_bobber_y = None
        
        # 🎣 Casting time setting
        self.min_cast_time = 0.15
        self.max_cast_time = 0.35
        
        # Bobber detection and minigame state
        self.consecutive_match_fail_count = 0
        self.MAX_MATCH_FAIL_COUNT = 2
        self.current_minigame_region = None # Absolute region of the dynamically found minigame bar (x, y, w, h)
        
        # Safe mouse area
        screen_width, screen_height = pyautogui.size()
        self.SAFE_MOUSE_POS = (screen_width - 50, screen_height - 50)
        
    def _get_roi_monitor(self, full_area, last_center, radius):
        """
        Calculates a monitor dict for MSS centered around the last known bobber position,
        but constrained within the full casting area.
        Returns the monitor dict and the offset of the new ROI relative to the full area's top-left corner.
        """
        x_root, y_root, w_root, h_root = full_area
        center_x_rel, center_y_rel = last_center

        # Calculate coordinates for the new, smaller ROI (relative to screen)
        x_roi = x_root + center_x_rel - radius
        y_roi = y_root + center_y_rel - radius
        w_roi = radius * 2
        h_roi = radius * 2

        # Clamp ROI to the boundaries of the full casting area
        
        # X clamping
        x_start_clamped = max(x_roi, x_root)
        x_end_clamped = min(x_roi + w_roi, x_root + w_root)
        
        # Y clamping
        y_start_clamped = max(y_roi, y_root)
        y_end_clamped = min(y_roi + h_roi, y_root + h_root)
        
        final_w = x_end_clamped - x_start_clamped
        final_h = y_end_clamped - y_start_clamped
        
        # If the constrained area is too small, revert to full area (should not happen if initial detection is inside)
        if final_w < 10 or final_h < 10:
            return None, (0, 0) # Fallback indicator
        
        # The offset is the distance from the full area's top-left to the ROI's top-left
        # This is needed to translate template match results (relative to ROI) back to
        # coordinates relative to the full casting area.
        offset_x_rel_to_full = x_start_clamped - x_root
        offset_y_rel_to_full = y_start_clamped - y_root
        
        monitor_roi = {
            "top": y_start_clamped, 
            "left": x_start_clamped, 
            "width": final_w, 
            "height": final_h
        }
        
        return monitor_roi, (offset_x_rel_to_full, offset_y_rel_to_full)


    def _load_template(self, filename):
        """Loads and validates the template image."""
        if not os.path.exists(filename):
            self.log(f"🛑 Required template file is missing: '{filename}'")
            return None
            
        template = cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
        
        if template is None:
            self.log(f"🛑 Template load failed: '{filename}'. File may be corrupted.")
            return None
            
        return template

    # --- Bot Control and Configuration ---
    def start_bot(self):
        if self.is_running.is_set():
             return

        if self.bobber_template is None or self.minigame_bar_template is None:
            self.log("🛑 Bot start failed: Some template images are missing.")
            return

        if not self.casting_area_ref["area"]:
            self.log("🛑 Bot start failed: Fishing area is not set.")
            return
            
        if win32gui and win32con:
            try:
                hwnd = win32gui.FindWindow(None, self.GAME_WINDOW_TITLE)
                if hwnd != 0:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.1)
                    self.log(f"✅ Game client focusing complete.")
            except Exception:
                self.log(f"❌ Focusing error. Please activate the window manually.")
        
        self.is_running.set()
        self.fishing_thread = threading.Thread(target=self.fishing_loop, daemon=True)
        self.fishing_thread.start()

    def stop_bot(self):
        """Stops the bot execution"""
        if self.is_running.is_set():
            self.is_running.clear()
        
    def set_cast_time(self, min_time, max_time):
        """Sets the bobber casting hold time"""
        self.min_cast_time = min_time
        self.max_cast_time = max_time
        
    def set_diff_threshold(self, threshold):
        """Sets the vertical drop threshold (reusing POSITION_DIFF_THRESHOLD)"""
        self.POSITION_DIFF_THRESHOLD = threshold

    # --- Bobber Detection and Bite Detection Logic ---
    def _get_bobber_image(self):
        """
        Captures the fishing area and finds the bobber using template matching.
        Uses dynamic ROI if a previous position is known for faster detection.
        """
        area = self.casting_area_ref["area"]
        if not area or self.bobber_template is None:
            return None, None, None

        x_root, y_root, w_root, h_root = area
        t_w, t_h = self.bobber_template.shape[::-1]
        
        # 1. Determine Capture Monitor and Offset
        offset_x_rel_to_full = 0
        offset_y_rel_to_full = 0
        
        # Try to use ROI if previous successful position exists
        if self.previous_bobber_image and self.previous_bobber_image[2]:
            last_center_rel = self.previous_bobber_image[2]
            monitor_roi, offset = self._get_roi_monitor(area, last_center_rel, self.BOBBER_SEARCH_RADIUS)
            
            if monitor_roi:
                monitor_to_use = monitor_roi
                offset_x_rel_to_full, offset_y_rel_to_full = offset
            else:
                # Fallback to full casting area if ROI calculation failed
                monitor_to_use = {"top": y_root, "left": x_root, "width": w_root, "height": h_root}
        else:
            # Use full casting area for initial detection
            monitor_to_use = {"top": y_root, "left": x_root, "width": w_root, "height": h_root}

        # 2. Capture Screenshot and Process
        with mss.mss() as sct_local:
            try:
                # Capture the defined area (either full area or ROI)
                full_screenshot = sct_local.grab(monitor_to_use)
                
                img_array = np.array(full_screenshot, dtype=np.uint8)
                img_array_bgr = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)
                gray_img = cv2.cvtColor(img_array_bgr, cv2.COLOR_BGR2GRAY)
                
                result = cv2.matchTemplate(gray_img, self.bobber_template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                best_rect = None
                bobber_center = None
                
                if max_val >= self.MATCH_THRESHOLD:
                    # Coordinates are relative to the monitor_to_use area
                    top_left_roi = max_loc
                    x_roi, y_roi = top_left_roi
                    w, h = t_w, t_h
                    
                    # Convert coordinates back to being relative to the full casting area (x_root, y_root)
                    x_full_rel = x_roi + offset_x_rel_to_full
                    y_full_rel = y_roi + offset_y_rel_to_full
                    
                    best_rect = (x_full_rel, y_full_rel, w, h)
                    
                    x_center = x_full_rel + w // 2
                    y_center = y_full_rel + h // 2
                    bobber_center = (x_center, y_center)
                    self.consecutive_match_fail_count = 0
                
                
                # Generate debug image (always capture the full casting area for consistent UI output)
                monitor_root = {"top": y_root, "left": x_root, "width": w_root, "height": h_root}
                full_pil_img = Image.fromarray(cv2.cvtColor(
                    np.array(sct_local.grab(monitor_root), dtype=np.uint8)[:,:,:3], 
                    cv2.COLOR_BGR2RGB))
                
                debug_img = full_pil_img.copy()
                draw = ImageDraw.Draw(debug_img)
                
                if best_rect:
                    x, y, w, h = best_rect
                    draw.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=2)
                else:
                    self.consecutive_match_fail_count += 1
                    cx, cy = w_root // 2, h_root // 2
                    draw.rectangle([cx-10, cy-10, cx+10, cy+10], outline=(255, 0, 0), width=2)
                    draw.text((10, 10), f"Match FAIL ({max_val:.2f})", fill=(255, 0, 0))

                self.debug_img_callback(debug_img)

                if best_rect:
                    # Returns a grayscale cropped image around the bobber.
                    bobber_crop_pil = full_pil_img.crop((x, y, x + w, y + h)).convert('L')
                    return bobber_crop_pil, (t_w, t_h), bobber_center
                
                return None, None, None

            except Exception as e:
                self.log(f"Error during capture and template matching: {e}")
                if area:
                    self.debug_img_callback(Image.new('RGB', (w_root, h_root), color = 'black'))
                return None, None, None

        x_root, y_root, w_root, h_root = area
        t_w, t_h = self.bobber_template.shape[::-1]

        with mss.mss() as sct_local:
            try:
                monitor_root = {"top": y_root, "left": x_root, "width": w_root, "height": h_root}
                full_screenshot = sct_local.grab(monitor_root)
                
                img_array = np.array(full_screenshot, dtype=np.uint8)
                img_array_bgr = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)
                gray_img = cv2.cvtColor(img_array_bgr, cv2.COLOR_BGR2GRAY)
                
                result = cv2.matchTemplate(gray_img, self.bobber_template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                best_rect = None
                bobber_center = None
                
                if max_val >= self.MATCH_THRESHOLD:
                    top_left = max_loc
                    x, y = top_left
                    w, h = t_w, t_h
                    best_rect = (x, y, w, h)
                    
                    x_center = x + w // 2
                    y_center = y + h // 2
                    bobber_center = (x_center, y_center)
                    self.consecutive_match_fail_count = 0
                
                
                # Generate debug image
                full_pil_img = Image.fromarray(cv2.cvtColor(img_array_bgr, cv2.COLOR_BGR2RGB))
                debug_img = full_pil_img.copy()
                draw = ImageDraw.Draw(debug_img)
                
                if best_rect:
                    draw.rectangle([x, y, x + w, y + h], outline=(0, 255, 0), width=2)
                else:
                    self.consecutive_match_fail_count += 1
                    cx, cy = w_root // 2, h_root // 2
                    draw.rectangle([cx-10, cy-10, cx+10, cy+10], outline=(255, 0, 0), width=2)
                    draw.text((10, 10), f"Match FAIL ({max_val:.2f})", fill=(255, 0, 0))

                self.debug_img_callback(debug_img)

                if best_rect:
                    # Returns a grayscale cropped image around the bobber.
                    bobber_crop_pil = full_pil_img.crop((x, y, x + w, y + h)).convert('L')
                    return bobber_crop_pil, (t_w, t_h), bobber_center
                
                return None, None, None

            except Exception as e:
                self.log(f"Error during capture and template matching: {e}")
                if area:
                     self.debug_img_callback(Image.new('RGB', (w_root, h_root), color = 'black'))
                return None, None, None

    def _check_for_bite(self):
        """
        Bite detection logic. Detects the vertical drop distance of the bobber compared to its initial resting position.
        🚨 Real-time Y coordinate logging is implemented inside this method.
        """
        current_gray_image, current_search_size, current_center = self._get_bobber_image()
        
        if current_gray_image is None or current_search_size is None:
            return False

        # 2. Initialization or if initial Y coordinate is not set
        if self.previous_bobber_image is None or self.initial_bobber_y is None:
            self.previous_bobber_image = (current_gray_image, current_search_size, current_center)
            return False
        
        # 3. 🚨 Detect and log vertical drop distance of current bobber relative to initial position
        
        current_y = current_center[1]
        
        # A larger Y value means lower (drop).
        y_distance = current_y - self.initial_bobber_y

        # 🚨 Real-time Y coordinate logging
        # (Output very concisely for frequent logging)
        # self.log(f"   [Y-TRACK] Cur: {current_y} / Dist: {y_distance:.1f} / Thr: {self.POSITION_DIFF_THRESHOLD}")
        
        # If y_distance is greater than or equal to the threshold (30), consider it a bite
        if y_distance >= self.POSITION_DIFF_THRESHOLD:
            self.log(f"🚨 [DETECTION] Bobber drop distance exceeded! (Drop distance:{y_distance}, Threshold:{self.POSITION_DIFF_THRESHOLD}). Considering it a bite.")
            # Update previous_bobber_image since the bobber position moved.
            self.previous_bobber_image = (current_gray_image, current_search_size, current_center)
            return True
            
        # Save current image for next frame comparison
        self.previous_bobber_image = (current_gray_image, current_search_size, current_center)

        return False
        
    def cast_fishing_rod(self):
        """Performs the action of casting the fishing bobber"""
        area = self.casting_area_ref["area"]
        if not area:
            self.log("🛑 Bobber cast failed: Fishing area is not set.")
            return

        min_time = self.min_cast_time
        max_time = self.max_cast_time
        hold_time = random.uniform(min_time, max_time)

        x, y, w, h = area
        center_x = x + w // 2
        center_y = y + h // 2
        # Keep random offset for casting position
        offset_x = random.randint(-10, 10)
        offset_y = random.randint(-10, 10)
        target_x = center_x + offset_x
        target_y = center_y + offset_y
        
        pyautogui.moveTo(target_x, target_y, duration=0.1)
        pyautogui.mouseDown(button='left')
        time.sleep(hold_time)
        pyautogui.mouseUp(button='left')
        
        self.log(f"✅ Fishing bobber cast complete. Hold time: {hold_time:.2f} seconds.")
        pyautogui.moveTo(self.SAFE_MOUSE_POS[0], self.SAFE_MOUSE_POS[1], duration=0.01)

    # --- Find Minigame Bar Region ---
    def _find_minigame_bar_region(self):
        """Searches the entire screen for the minigame bar using template matching and returns the absolute region (x, y, w, h)."""
        if self.minigame_bar_template is None:
            self.log("🛑 Minigame bar template is not loaded.")
            return None

        t_w, t_h = self.minigame_bar_template.shape[::-1]
        
        with mss.mss() as sct_local:
            monitor_full = sct_local.monitors[0]
            full_screenshot = sct_local.grab(monitor_full)
            
            img_array = np.array(full_screenshot, dtype=np.uint8)
            img_array_bgr = cv2.cvtColor(img_array, cv2.COLOR_BGRA2BGR)
            gray_img = cv2.cvtColor(img_array_bgr, cv2.COLOR_BGR2GRAY)
            
            # Change MATCH_THRESHOLD to 0.5 (0.5 is appropriate if the template matches well)
            result = cv2.matchTemplate(gray_img, self.minigame_bar_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= 0.5:
                x, y = max_loc
                region = (x, y, t_w, t_h)
                self.current_minigame_region = region # Store in class variable
                return region
                
            return None

    # --- Minigame Loop (based on blog rolling() logic) ---
    def minigame_loop(self):
        """Implements the rolling() function logic from the blog (reflects 1/3 probability delay upon reeling release)"""
        # self.log("🕹️ Starting minigame automation (based on blog logic)...") # Commented out for loop speed

        minigame_start_time = time.time()
        
        if self.current_minigame_region is None:
            self.log("🛑 Minigame region is not set, cannot start loop.")
            return False

        # Create local capture instance (to prevent thread errors)
        try:
            sct_local = mss.mss()
        except Exception as e:
            self.log(f"🛑 Minigame capture initialization error: {e}")
            return False

        # Call mouseUp just in case of a previous click
        pyautogui.mouseUp(button='left')
        
        # Absolute coordinates of the bar
        x_bar, y_bar, w_bar, h_bar = self.current_minigame_region
        
        while self.is_running.is_set() and (time.time() - minigame_start_time) < self.MINIGAME_TIMEOUT:
            
            # Calculate capture region
            center_x = x_bar + w_bar // 2
            x_scan_start = center_x - self.MINIGAME_SCAN_WIDTH // 2
            y_scan_start = y_bar + self.MINIGAME_SCAN_Y_OFFSET
            
            scan_monitor = {
                "top": y_scan_start,
                "left": x_scan_start,
                "width": self.MINIGAME_SCAN_WIDTH,
                "height": 1
            }

            try:
                # 1. Capture 1-pixel line
                sct_img = sct_local.grab(scan_monitor)
                img_pil = Image.frombytes('RGB', (self.MINIGAME_SCAN_WIDTH, 1), sct_img.rgb)
                
                found_bright_pixel = False
                
                # 2. Pixel scan and control
                for i in range(self.MINIGAME_SCAN_WIDTH):
                    r, g, b = img_pil.getpixel((i, 0))
                    
                    if r + g + b > self.ROLL_LIMIT:
                        
                        found_bright_pixel = True
                        
                        if i <= self.MINIGAME_REEL_STOP_X:
                            pyautogui.mouseDown(button='left')
                            
                        elif i > self.MINIGAME_REEL_STOP_X:
                            # Release reeling
                            pyautogui.mouseUp(button='left')
                            
                            # 🚨 Apply 0.2~0.3 second delay with 1/3 probability after reeling release (hold)
                            if random.random() < (1/3):
                                delay = random.uniform(0.2, 0.3)
                                # self.log(f"   [Minigame] Applying random delay: {delay:.2f}s") # Commented out for loop speed
                                time.sleep(delay)
                            
                        break
                        
                
                # When scanning to the end without finding a bright pixel (window closed due to minigame success/failure)
                if not found_bright_pixel:
                    pyautogui.mouseUp(button='left')
                    pyautogui.leftClick() # Interpreted as clicking the fishing end button (safe reeling release)
                    self.log("🎉 Target area disappearance detected! Minigame loop terminated.")
                    return True
                
            except Exception as e:
                self.log(f"Minigame tracking error: {e}")
                pyautogui.mouseUp(button='left')
                return False
            
            time.sleep(0.001)

        self.log("🛑 Minigame timeout or stop requested.")
        pyautogui.mouseUp(button='left')
        return False

    # --- Main Loop ---
    def fishing_loop(self):
        self.log("🤖 Entering fishing loop.")
        
        if self.bobber_template is None:
             self.log("🛑 Cannot start fishing loop due to template load failure.")
             self.is_running.clear()
             return

        while self.is_running.is_set():
            start_time = time.time()
            try:
                self.previous_bobber_image = None
                self.consecutive_match_fail_count = 0
                self.current_minigame_region = None
                self.initial_bobber_y = None # 🚨 Initialization at loop start
                
                # 1. Cast bobber
                self.cast_fishing_rod()
                time.sleep(2.0)
                if not self.is_running.is_set(): break

                # 2. Detect initial bobber image
                initial_check_success = False
                MAX_ATTEMPTS = 5
                self.log("⏳ Attempting bobber landing and initial image detection...")
                
                for attempt in range(MAX_ATTEMPTS):
                    current_bobber_image, current_search_size, current_center = self._get_bobber_image()
                    
                    if current_bobber_image is not None:
                        self.previous_bobber_image = (current_bobber_image, current_search_size, current_center)
                        self.initial_bobber_y = current_center[1] # 🚨 Store initial Y coordinate
                        self.log(f"✅ Bobber landing and initial image save successful (Initial Y: {self.initial_bobber_y}).")
                        initial_check_success = True
                        break
                    
                    if not self.is_running.is_set(): break
                    time.sleep(0.2)

                if not initial_check_success:
                    if self.is_running.is_set():
                        self.log(f"⚠️ Initial bobber landing detection failed. Recasting in 1 seconds.")
                        time.sleep(1.0)
                    if not self.is_running.is_set(): break
                    continue
                
                self.log(f"✅ Minimum drop threshold: {self.POSITION_DIFF_THRESHOLD} pixels.")

                # 3. Wait for bite detection (max 30 seconds)
                max_wait_time = 30
                self.is_bite_detected.clear()
                
                bite_start_time = time.time()
                
                while self.is_running.is_set() and (time.time() - bite_start_time) < max_wait_time:
                    
                    if self._check_for_bite():
                        self.is_bite_detected.set()
                        break
                        
                    # 🚨 Logging is handled inside _check_for_bite, so only time measurement is done here.
                    time.sleep(0.001) # Minimum wait time to reduce CPU load
                    
                if not self.is_running.is_set(): break

                # 4. Confirm bite and enter minigame
                if self.is_bite_detected.is_set():
                    
                    # 4-A. Apply 0.5 ~ 1.0 second random delay
                    click_delay = random.uniform(0.5, 1.0)
                    self.log(f"🚨 Bite detection successful! Clicking after {click_delay:.2f} seconds.")
                    time.sleep(click_delay)

                    # 4-B. Calculate bobber center click position and random adjustment
                    if self.previous_bobber_image and len(self.previous_bobber_image) > 2:
                         x_root, y_root, _, _ = self.casting_area_ref["area"]
                         
                         # Bobber center coordinates (relative coordinates)
                         center_x_rel = self.previous_bobber_image[2][0]
                         center_y_rel = self.previous_bobber_image[2][1]

                         # 🎣 Random offset (reduced to +-5 pixels for improved accuracy)
                         offset_x = random.randint(-5, 5)
                         offset_y = random.randint(-5, 5)

                         # Final click coordinates (absolute coordinates)
                         click_x = x_root + center_x_rel + offset_x
                         click_y = y_root + center_y_rel + offset_y

                         pyautogui.moveTo(click_x, click_y, duration=0.1)
                         pyautogui.click()
                         self.log(f"✅ Click around bobber complete. (offset: {offset_x}, {offset_y})")
                    else:
                         pyautogui.click()
                         self.log("✅ Last cast position click complete.")

                    
                    # 4-1. Find minigame bar position (retry logic added)
                    self.log(f"🔍 Dynamically searching for minigame bar location (max {self.MAX_BAR_SEARCH_ATTEMPTS} retries)...")
                    
                    bar_region = None
                    for attempt in range(self.MAX_BAR_SEARCH_ATTEMPTS):
                        bar_region = self._find_minigame_bar_region()
                        
                        if bar_region is not None:
                            self.current_minigame_region = bar_region
                            self.log(f"✅ Minigame bar detection successful. (Attempt {attempt+1})")
                            break
                        
                        if not self.is_running.is_set(): return
                        
                        # Wait briefly if not found
                        time.sleep(self.BAR_SEARCH_INTERVAL)
                        self.log(f"   [Bar Detection] Failed. {attempt+1} / {self.MAX_BAR_SEARCH_ATTEMPTS} retrying...")
                    
                    if bar_region is None:
                        self.log("🛑 Minigame bar detection failed finally! Skipping minigame.")
                        # Maintain 5.0 seconds wait time until the minigame window closes
                        time.sleep(5.0)
                        # Post-minigame failure process (move to the next fishing loop)
                    else:
                        # 4-2. Call minigame loop
                        detection_delay = time.time() - start_time
                        self.log(f"Delay: {detection_delay:.3f} seconds. Starting minigame.")
                        self.minigame_loop()
                    
                    if not self.is_running.is_set(): break

                    # 4-3. Post-processing
                    self.log("🔑 Post-processing: Press Cancel key (S) and wait 1 second.")
                    pyautogui.press('s')
                    time.sleep(1.0)
                    
                    # Randomly set rest time after fishing
                    sleep_duration = random.uniform(0.5, 1.2)
                    self.log(f"😴 Resting for {sleep_duration:.2f} seconds...")
                    time.sleep(sleep_duration)
                    if not self.is_running.is_set(): break

                elif self.is_running.is_set():
                    self.log("⌛ Bite detection time exceeded (30 seconds).")
                    
                    self.log("🔑 Press Cancel key (S) and wait 1 second after timeout.")
                    pyautogui.press('s')
                    time.sleep(1.0)
                    
                    self.log("Waiting 2 seconds for the next loop.")
                    time.sleep(2.0)
                    if not self.is_running.is_set(): break

            except Exception as e:
                self.log(f"❌ Error occurred during fishing loop: {e}")
                self.log(traceback.format_exc())
                self.is_running.clear()
                break
        
        self.is_running.clear()
        self.log("😴 Fishing bot routine terminated finally.")
