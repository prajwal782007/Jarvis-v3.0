import os
import subprocess
import sys
import logging
import asyncio
from fuzzywuzzy import process
from livekit.agents import function_tool

try:
    import pygetwindow as gw
except ImportError:
    gw = None

sys.stdout.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_safe_index_directories() -> list[str]:
    """Returns accessible directories for searching media/files."""
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

async def focus_window(title_keyword: str) -> bool:
    if not gw:
        logger.warning("⚠ pygetwindow not available")
        return False

    await asyncio.sleep(1.0)
    title_keyword = title_keyword.lower().strip()

    for window in gw.getAllWindows():
        if title_keyword in window.title.lower():
            if window.isMinimized:
                window.restore()
            window.activate()
            logger.info(f"🪟 window focus में है: {window.title}")
            return True
    logger.warning("⚠ Focus करने के लिए window नहीं मिली।")
    return False

def _sync_index_files(base_dirs: list[str], max_items: int = 5000) -> list[dict]:
    file_index = []
    for base_dir in base_dirs:
        if not os.path.exists(base_dir):
            continue
        try:
            for root, _, files in os.walk(base_dir):
                for f in files:
                    file_index.append({
                        "name": f,
                        "path": os.path.join(root, f),
                        "type": "file"
                    })
                    if len(file_index) >= max_items:
                        return file_index
        except Exception as e:
            logger.warning(f"Error scanning directory '{base_dir}': {e}")
    logger.info(f"✅ Indexed {len(file_index)} files.")
    return file_index

async def index_files(base_dirs: list[str]) -> list[dict]:
    return await asyncio.to_thread(_sync_index_files, base_dirs)

def _sync_search_file(query: str, index: list[dict]) -> dict | None:
    choices = [item["name"] for item in index]
    if not choices:
        logger.warning("⚠ Match करने के लिए कोई files नहीं हैं।")
        return None

    best_match, score = process.extractOne(query, choices)
    logger.info(f"🔍 Matched '{query}' to '{best_match}' (Score: {score})")
    if score > 70:
        for item in index:
            if item["name"] == best_match:
                return item
    return None

async def search_file(query: str, index: list[dict]) -> dict | None:
    return await asyncio.to_thread(_sync_search_file, query, index)

async def open_file(item: dict) -> str:
    try:
        logger.info(f"📂 File खोल रहे हैं: {item['path']}")
        if os.name == 'nt':
            os.startfile(item["path"])
        else:
            subprocess.call(['open' if sys.platform == 'darwin' else 'xdg-open', item["path"]])
        await focus_window(item["name"])
        return f"✅ File open हो गई।: {item['name']}"
    except Exception as e:
        logger.error(f"❌ File open करने में error आया।: {e}")
        return f"❌ File open करने में विफल रहा। {e}"

async def handle_command(command: str, index: list[dict]) -> str:
    item = await search_file(command, index)
    if item:
        return await open_file(item)
    else:
        logger.warning("❌ File नहीं मिली।")
        return "❌ File नहीं मिली।"

@function_tool
async def Play_file(name: str) -> str:
    folders_to_index = get_safe_index_directories()
    index = await index_files(folders_to_index)
    command = name.strip()
    return await handle_command(command, index)
