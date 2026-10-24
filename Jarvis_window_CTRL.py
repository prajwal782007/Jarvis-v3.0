import os
import subprocess
import logging
import sys
import asyncio
import shutil
from typing import Optional, Tuple
from fuzzywuzzy import process

from security import auth_manager

try:
    from livekit.agents import function_tool
except ImportError:
    def function_tool(func): 
        return func

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None
    win32con = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

# Setup encoding and logger
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------
# Dynamic Application Resolver
# -------------------------
def resolve_application(app_title: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Dynamically resolves application executables without hardcoding user-specific paths.
    Returns (executable_command, focus_keyword). Returns (None, None) if not found.
    """
    app_norm = app_title.lower().strip()

    # 1. Standard Windows Built-ins & System Utilities
    built_ins = {
        "notepad": ("notepad", "notepad"),
        "calculator": ("calc", "calculator"),
        "calc": ("calc", "calculator"),
        "command prompt": ("cmd", "cmd"),
        "cmd": ("cmd", "cmd"),
        "control panel": ("control", "control panel"),
        "control": ("control", "control panel"),
        "paint": ("mspaint", "paint"),
        "mspaint": ("mspaint", "paint"),
        "settings": ("start ms-settings:", "settings"),
        "task manager": ("taskmgr", "task manager"),
        "taskmgr": ("taskmgr", "task manager"),
        "explorer": ("explorer", "file explorer"),
    }
    if app_norm in built_ins:
        return built_ins[app_norm]

    def _find_first_existing(candidates: list[str]) -> Optional[str]:
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")

    # 2. VS Code / Code
    if app_norm in ("vs code", "vscode", "code", "visual studio code"):
        which_path = shutil.which("code")
        if which_path:
            return which_path, "Visual Studio Code"
        found = _find_first_existing([
            os.path.join(local_app_data, "Programs", "Microsoft VS Code", "Code.exe"),
            os.path.join(program_files, "Microsoft VS Code", "Code.exe"),
            os.path.join(program_files_x86, "Microsoft VS Code", "Code.exe"),
        ])
        if found:
            return f'"{found}"', "Visual Studio Code"
        return None, None

    # 3. Postman
    if app_norm == "postman":
        which_path = shutil.which("postman")
        if which_path:
            return which_path, "Postman"
        found = _find_first_existing([
            os.path.join(local_app_data, "Postman", "Postman.exe"),
            os.path.join(local_app_data, "Programs", "Postman", "Postman.exe"),
            os.path.join(program_files, "Postman", "Postman.exe"),
        ])
        if found:
            return f'"{found}"', "Postman"
        return None, None

    # 4. Google Chrome
    if app_norm in ("chrome", "google chrome"):
        which_path = shutil.which("chrome")
        if which_path:
            return which_path, "Chrome"
        found = _find_first_existing([
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
        ])
        if found:
            return f'"{found}"', "Chrome"
        return None, None

    # 5. VLC Media Player
    if app_norm in ("vlc", "vlc media player"):
        which_path = shutil.which("vlc")
        if which_path:
            return which_path, "VLC"
        found = _find_first_existing([
            os.path.join(program_files, "VideoLAN", "VLC", "vlc.exe"),
            os.path.join(program_files_x86, "VideoLAN", "VLC", "vlc.exe"),
        ])
        if found:
            return f'"{found}"', "VLC"
        return None, None

    # 6. Microsoft Edge
    if app_norm in ("edge", "microsoft edge"):
        which_path = shutil.which("msedge")
        if which_path:
            return which_path, "Edge"
        found = _find_first_existing([
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        ])
        if found:
            return f'"{found}"', "Edge"
        return None, None

    # 7. Check if command exists anywhere on system PATH
    which_path = shutil.which(app_norm)
    if which_path:
        return which_path, app_norm

    return None, None

# -------------------------
# Safe Directory Discovery
# -------------------------
def get_safe_index_directories() -> list[str]:
    """Returns valid existing base directories for searching and indexing."""
    candidates = []
    if os.path.exists("D:/"):
        candidates.append("D:/")
    docs = os.path.expanduser("~/Documents")
    if os.path.exists(docs):
        candidates.append(docs)
    desktop = os.path.expanduser("~/Desktop")
    if os.path.exists(desktop):
        candidates.append(desktop)
    return candidates or [os.path.expanduser("~")]

# -------------------------
# Global focus utility
# -------------------------
async def focus_window(title_keyword: str) -> bool:
    if not gw:
        logger.warning("⚠ pygetwindow not available")
        return False

    await asyncio.sleep(1.0)  # Give time for window to appear
    title_keyword = title_keyword.lower().strip()

    for window in gw.getAllWindows():
        if title_keyword in window.title.lower():
            if window.isMinimized:
                window.restore()
            window.activate()
            return True
    return False

# -------------------------
# Non-blocking Indexing & Search
# -------------------------
def _sync_index_items(base_dirs: list[str], max_items: int = 5000) -> list[dict]:
    item_index = []
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
        try:
            for root, dirs, files in os.walk(base_dir):
                for d in dirs:
                    item_index.append({"name": d, "path": os.path.join(root, d), "type": "folder"})
                    if len(item_index) >= max_items:
                        return item_index
                for f in files:
                    item_index.append({"name": f, "path": os.path.join(root, f), "type": "file"})
                    if len(item_index) >= max_items:
                        return item_index
        except Exception as e:
            logger.warning(f"Error indexing {base_dir}: {e}")
    logger.info(f"✅ Indexed {len(item_index)} items.")
    return item_index

async def index_items(base_dirs: list[str]) -> list[dict]:
    return await asyncio.to_thread(_sync_index_items, base_dirs)

def _sync_search_item(query: str, index: list[dict], item_type: str) -> Optional[dict]:
    filtered = [item for item in index if item["type"] == item_type]
    choices = [item["name"] for item in filtered]
    if not choices:
        return None
    best_match, score = process.extractOne(query, choices)
    logger.info(f"🔍 Matched '{query}' to '{best_match}' with score {score}")
    if score > 70:
        for item in filtered:
            if item["name"] == best_match:
                return item
    return None

async def search_item(query: str, index: list[dict], item_type: str) -> Optional[dict]:
    return await asyncio.to_thread(_sync_search_item, query, index, item_type)

# File/folder actions
async def open_folder(path: str):
    try:
        os.startfile(path) if os.name == 'nt' else subprocess.call(['xdg-open', path])
        await focus_window(os.path.basename(path))
    except Exception as e:
        logger.error(f"❌ Folder open error: {e}")

async def play_file(path: str):
    try:
        os.startfile(path) if os.name == 'nt' else subprocess.call(['xdg-open', path])
        await focus_window(os.path.basename(path))
    except Exception as e:
        logger.error(f"❌ File open error: {e}")

async def create_folder(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
        return f"✅ Folder create हो गया।: {path}"
    except Exception as e:
        return f"❌ Folder create करने में error आया।: {e}"

async def rename_item(old_path: str, new_path: str) -> str:
    try:
        os.rename(old_path, new_path)
        return f"✅ नाम बदलकर {new_path} कर दिया गया।"
    except Exception as e:
        return f"❌ नाम बदलना fail हो गया: {e}"

async def delete_item(path: str) -> str:
    # Explicit authorization check before file or directory deletion
    allowed, msg = auth_manager.check_authorization("file_delete", details=f"path: {path}")
    if not allowed:
        return msg

    try:
        if os.path.isdir(path):
            os.rmdir(path)
        else:
            os.remove(path)
        return f"🗑️ Deleted: {path}"
    except Exception as e:
        return f"❌ Delete नहीं हुआ।: {e}"

# -------------------------
# App Control Tool
# -------------------------
@function_tool
async def launch_application(app_title: str) -> str:
    """
    Launches an application dynamically and brings its window into focus.
    Replaces previously shadowed 'open' function.
    """
    app_title = app_title.strip()
    cmd, focus_target = resolve_application(app_title)

    if not cmd:
        logger.warning(f"Could not find application: {app_title}")
        return f"❌ Application '{app_title}' could not be found on this system. Please check if it is installed or specify a valid path."

    try:
        if cmd.startswith("start "):
            await asyncio.create_subprocess_shell(cmd, shell=True)
        else:
            await asyncio.create_subprocess_shell(f'start "" {cmd}', shell=True)

        target = focus_target or app_title
        focused = await focus_window(target)
        if focused:
            return f"🚀 App launch हुआ और focus में है: {app_title}."
        else:
            return f"🚀 {app_title} Launch किया गया, लेकिन window पर focus नहीं हो पाया।"
    except Exception as e:
        return f"❌ {app_title} Launch नहीं हो पाया।: {e}"

# Backwards compatibility alias
open = launch_application

@function_tool
async def close(window_title: str) -> str:
    if not win32gui:
        return "❌ win32gui not available"

    def enumHandler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if window_title.lower() in win32gui.GetWindowText(hwnd).lower():
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    win32gui.EnumWindows(enumHandler, None)
    return f"❌ Window बंद हो गई है।: {window_title}"

# -------------------------
# Jarvis Command Logic
# -------------------------
@function_tool
async def folder_file(command: str) -> str:
    folders_to_index = get_safe_index_directories()
    index = await index_items(folders_to_index)
    command_lower = command.lower()

    if "create folder" in command_lower:
        folder_name = command.replace("create folder", "").strip()
        base = folders_to_index[0]
        path = os.path.join(base, folder_name)
        return await create_folder(path)

    if "rename" in command_lower:
        parts = command_lower.replace("rename", "").strip().split("to")
        if len(parts) == 2:
            old_name = parts[0].strip()
            new_name = parts[1].strip()
            item = await search_item(old_name, index, "folder")
            if item:
                new_path = os.path.join(os.path.dirname(item["path"]), new_name)
                return await rename_item(item["path"], new_path)
        return "❌ rename command valid नहीं है।"

    if "delete" in command_lower:
        item = await search_item(command, index, "folder") or await search_item(command, index, "file")
        if item:
            # Gated by authorization check inside delete_item
            return await delete_item(item["path"])
        return "❌ Delete करने के लिए item नहीं मिला।"

    if "folder" in command_lower or "open folder" in command_lower:
        item = await search_item(command, index, "folder")
        if item:
            await open_folder(item["path"])
            return f"✅ Folder opened: {item['name']}"
        return "❌ Folder नहीं मिला।."

    item = await search_item(command, index, "file")
    if item:
        await play_file(item["path"])
        return f"✅ File opened: {item['name']}"

    return "⚠ कुछ भी match नहीं हुआ।"
