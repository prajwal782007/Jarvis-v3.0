import os
import requests
import logging
import asyncio
from dotenv import load_dotenv
from livekit.agents import function_tool
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _sync_fetch_google_search(url: str, params: dict) -> requests.Response:
    """Synchronous network fetch with timeout to run in a worker thread."""
    return requests.get(url, params=params, timeout=10)

@function_tool
async def google_search(query: str) -> str:
    logger.info(f"Query प्राप्त हुई।: {query}")

    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    search_engine_id = os.getenv("SEARCH_ENGINE_ID")

    if not api_key or not search_engine_id:
        logger.error("API key या Search Engine ID missing है।")
        return "Environment variables में API key या Search Engine ID missing है।"

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        "num": 3
    }

    logger.info("Google Custom Search API को request भेजी जा रही है...")
    try:
        # Offload synchronous network I/O to a worker thread to avoid blocking the asyncio event loop
        response = await asyncio.to_thread(_sync_fetch_google_search, url, params)
    except requests.exceptions.Timeout:
        logger.error("Google Search API request timed out.")
        return "Google Search API request time out हो गई।"
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Search request failed: {e}")
        return f"Google Search request विफल रही: {e}"

    if response.status_code != 200:
        logger.error(f"Google API में error आया: {response.status_code} - {response.text}")
        return f"Google Search API में error आया: {response.status_code} - {response.text}"

    data = response.json()
    results = data.get("items", [])

    if not results:
        logger.info("कोई results नहीं मिले।")
        return "कोई results नहीं मिले।"

    formatted = ""
    logger.info("Search results:")
    for i, item in enumerate(results, start=1):
        title = item.get("title", "No title")
        link = item.get("link", "No link")
        snippet = item.get("snippet", "")
        formatted += f"{i}. {title}\n{link}\n{snippet}\n\n"
        logger.info(f"{i}. {title}\n{link}\n{snippet}\n")

    return formatted.strip()

@function_tool
async def get_current_datetime() -> str:
    return datetime.now().isoformat()
