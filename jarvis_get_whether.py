import os
import requests
import logging
import asyncio
from dotenv import load_dotenv
from livekit.agents import function_tool

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _sync_detect_city_by_ip() -> str:
    try:
        logger.info("IP के ज़रिए शहर detect करने की कोशिश की जा रही है")
        response = requests.get("https://ipapi.co/json/", timeout=5)
        ip_info = response.json()
        city = ip_info.get("city")
        if city:
            logger.info(f"IP से शहर Detect किया गया: {city}")
            return city
        else:
            logger.warning("City detect करने में विफल, default 'Delhi' इस्तेमाल किया जा रहा है।")
            return "Delhi"
    except Exception as e:
        logger.error(f"IP से city detect करने में error आया: {e}")
        return "Delhi"

async def detect_city_by_ip() -> str:
    """Offloads IP detection HTTP request to a worker thread."""
    return await asyncio.to_thread(_sync_detect_city_by_ip)

def _sync_fetch_weather(url: str, params: dict) -> requests.Response:
    """Synchronous weather fetch with timeout to run in a worker thread."""
    return requests.get(url, params=params, timeout=10)

@function_tool
async def get_weather(city: str = "") -> str:
    api_key = os.getenv("OPENWEATHER_API_KEY")

    if not api_key:
        logger.error("OpenWeather API key missing है।")
        return "Environment variables में OpenWeather API key नहीं मिली।"

    if not city:
        city = await detect_city_by_ip()

    logger.info(f"City के लिए weather fetch किया जा रहा है।: {city}")
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric"
    }

    try:
        # Offload synchronous weather request to worker thread
        response = await asyncio.to_thread(_sync_fetch_weather, url, params)
        if response.status_code != 200:
            logger.error(f"OpenWeather API में error आया।: {response.status_code} - {response.text}")
            return f"Error: {city} के लिए weather fetch नहीं कर पाए। कृपया city name चेक करें।"

        data = response.json()
        weather = data["weather"][0]["description"].title()
        temperature = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]

        result = (f"Weather in {city}:\n"
                  f"- Condition: {weather}\n"
                  f"- Temperature: {temperature}°C\n"
                  f"- Humidity: {humidity}%\n"
                  f"- Wind Speed: {wind_speed} m/s")

        logger.info(f"Weather result: \n{result}")
        return result

    except requests.exceptions.Timeout:
        logger.error("Weather API request timed out.")
        return "Weather API request time out हो गई।"
    except Exception as e:
        logger.exception(f"Weather fetch करते समय exception आया: {e}")
        return f"Weather fetch करते समय एक error आया: {e}"
