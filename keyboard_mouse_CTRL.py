import pyautogui
import asyncio
import time
import logging
from datetime import datetime
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
from typing import List
from livekit.agents import function_tool

from security import auth_manager

logger = logging.getLogger(__name__)

# ---------------------
# SafeController Class
# ---------------------
class SafeController:
    def __init__(self):
        self.enabled = True
        self.keyboard = KeyboardController()
        self.mouse = MouseController()
        self.valid_keys = set("abcdefghijklmnopqrstuvwxyz1234567890")
        self.special_keys = {
            "enter": Key.enter, "space": Key.space, "tab": Key.tab,
            "shift": Key.shift, "ctrl": Key.ctrl, "alt": Key.alt,
            "esc": Key.esc, "backspace": Key.backspace, "delete": Key.delete,
            "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            "caps_lock": Key.caps_lock, "cmd": Key.cmd, "win": Key.cmd,
            "home": Key.home, "end": Key.end,
            "page_up": Key.page_up, "page_down": Key.page_down
        }

    def resolve_key(self, key):
        return self.special_keys.get(key.lower(), key)

    def log(self, action: str):
        try:
            with open("control_log.txt", "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()}: {action}\n")
        except Exception as e:
            logger.warning(f"Failed to write to control_log.txt: {e}")

    def is_active(self):
        return self.enabled

    async def move_cursor(self, direction: str, distance: int = 100):
        if not self.is_active():
            return "🛑 Controller is disabled."
        x, y = self.mouse.position
        if direction == "left":
            self.mouse.position = (x - distance, y)
        elif direction == "right":
            self.mouse.position = (x + distance, y)
        elif direction == "up":
            self.mouse.position = (x, y - distance)
        elif direction == "down":
            self.mouse.position = (x, y + distance)
        await asyncio.sleep(0.1)
        self.log(f"Mouse moved {direction}")
        return f"🖱️ Moved mouse {direction}."

    async def mouse_click(self, button: str = "left"):
        if not self.is_active():
            return "🛑 Controller is disabled."
        if button == "left":
            self.mouse.click(Button.left, 1)
        elif button == "right":
            self.mouse.click(Button.right, 1)
        elif button == "double":
            self.mouse.click(Button.left, 2)
        await asyncio.sleep(0.1)
        self.log(f"Mouse clicked: {button}")
        return f"🖱️ {button.capitalize()} click."

    async def scroll_cursor(self, direction: str, amount: int = 10):
        if not self.is_active():
            return "🛑 Controller is disabled."
        try:
            if direction == "up":
                self.mouse.scroll(0, amount)
            elif direction == "down":
                self.mouse.scroll(0, -amount)
        except Exception:
            pyautogui.scroll(amount * 100)
        await asyncio.sleep(0.1)
        self.log(f"Mouse scrolled {direction}")
        return f"🖱️ Scrolled {direction}"

    async def type_text(self, text: str):
        if not self.is_active():
            return "🛑 Controller is disabled."
        
        # Explicit authorization check for arbitrary keyboard input
        allowed, msg = auth_manager.check_authorization("arbitrary_typing", details=f"typing {len(text)} characters")
        if not allowed:
            return msg

        for char in text:
            if not char.isprintable():
                continue
            try:
                self.keyboard.press(char)
                self.keyboard.release(char)
                await asyncio.sleep(0.02)
            except Exception:
                continue
        self.log(f"Typed text: {text}")
        return f"⌨️ Typed: {text}"

    async def press_key(self, key: str):
        if not self.is_active():
            return "🛑 Controller is disabled."
        if key.lower() not in self.special_keys and key.lower() not in self.valid_keys:
            return f"❌ Invalid key: {key}"
        k = self.resolve_key(key)
        try:
            self.keyboard.press(k)
            self.keyboard.release(k)
        except Exception as e:
            return f"❌ Failed key: {key} — {e}"
        await asyncio.sleep(0.1)
        self.log(f"Pressed key: {key}")
        return f"⌨️ Key '{key}' pressed."

    async def press_hotkey(self, keys: List[str]):
        if not self.is_active():
            return "🛑 Controller is disabled."

        # Explicit authorization check for hotkeys (blocks destructive combinations like Alt+F4)
        allowed, msg = auth_manager.check_authorization("press_hotkey", details=f"hotkey {' + '.join(keys)}", keys=keys)
        if not allowed:
            return msg

        resolved = []
        for k in keys:
            if k.lower() not in self.special_keys and k.lower() not in self.valid_keys:
                return f"❌ Invalid key in hotkey: {k}"
            resolved.append(self.resolve_key(k))

        for k in resolved:
            self.keyboard.press(k)
        for k in reversed(resolved):
            self.keyboard.release(k)
        await asyncio.sleep(0.1)
        self.log(f"Pressed hotkey: {' + '.join(keys)}")
        return f"⌨️ Hotkey {' + '.join(keys)} pressed."

    async def control_volume(self, action: str):
        if not self.is_active():
            return "🛑 Controller is disabled."
        if action == "up":
            pyautogui.press("volumeup")
        elif action == "down":
            pyautogui.press("volumedown")
        elif action == "mute":
            pyautogui.press("volumemute")
        await asyncio.sleep(0.1)
        self.log(f"Volume control: {action}")
        return f"🔊 Volume {action}."

    async def swipe_gesture(self, direction: str):
        if not self.is_active():
            return "🛑 Controller is disabled."
        screen_width, screen_height = pyautogui.size()
        x, y = screen_width // 2, screen_height // 2
        try:
            if direction == "up":
                pyautogui.moveTo(x, y + 200)
                pyautogui.dragTo(x, y - 200, duration=0.3)
            elif direction == "down":
                pyautogui.moveTo(x, y - 200)
                pyautogui.dragTo(x, y + 200, duration=0.3)
            elif direction == "left":
                pyautogui.moveTo(x + 200, y)
                pyautogui.dragTo(x - 200, y, duration=0.3)
            elif direction == "right":
                pyautogui.moveTo(x - 200, y)
                pyautogui.dragTo(x + 200, y, duration=0.3)
        except Exception as e:
            logger.warning(f"Swipe failed: {e}")
        await asyncio.sleep(0.1)
        self.log(f"Swipe gesture: {direction}")
        return f"🖱️ Swipe {direction} done."

# ------------------------------
# LiveKit Tool Wrappers Section
# ------------------------------

controller = SafeController()

async def safe_execute(fn, *args, **kwargs):
    """Executes controller operations safely without arbitrary sleep lags or fake token bypasses."""
    try:
        return await fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error during controller action {fn.__name__}: {e}")
        return f"❌ Controller action failed: {e}"

# Backwards compatibility alias
with_temporary_activation = safe_execute

@function_tool
async def move_cursor_tool(direction: str, distance: int = 100):
    return await safe_execute(controller.move_cursor, direction, distance)

@function_tool
async def mouse_click_tool(button: str = "left"):
    return await safe_execute(controller.mouse_click, button)

@function_tool
async def scroll_cursor_tool(direction: str, amount: int = 10):
    return await safe_execute(controller.scroll_cursor, direction, amount)

@function_tool
async def type_text_tool(text: str):
    return await safe_execute(controller.type_text, text)

@function_tool
async def press_key_tool(key: str):
    return await safe_execute(controller.press_key, key)

@function_tool
async def press_hotkey_tool(keys: List[str]):
    return await safe_execute(controller.press_hotkey, keys)

@function_tool
async def control_volume_tool(action: str):
    return await safe_execute(controller.control_volume, action)

@function_tool
async def swipe_gesture_tool(direction: str):
    return await safe_execute(controller.swipe_gesture, direction)
