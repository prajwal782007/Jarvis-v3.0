import json
import os
import asyncio
import logging
from datetime import datetime, timedelta, date
from livekit.agents import function_tool

from memory_manager import memory_db

logger = logging.getLogger(__name__)

FILE = "schedule.json"

# Auto-migrate existing schedule.json on module load if file exists
try:
    if os.path.exists(FILE):
        migration_res = memory_db.migrate_schedule_json(FILE)
        if migration_res.get("migrated", 0) > 0:
            logger.info(f"Schedule auto-migration: {migration_res['migrated']} entries imported into SQLite.")
except Exception as e:
    logger.warning(f"Could not auto-migrate {FILE}: {e}")

def load_data():
    """Legacy helper: loads schedule.json safely."""
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_data(data):
    """Legacy helper: saves schedule.json safely with UTF-8 encoding."""
    try:
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to write legacy schedule.json: {e}")

@function_tool
async def add_schedule(date: str, task: str) -> str:
    """
    Saves a task or event for a specific date (YYYY-MM-DD or YYYY-MM-DD HH:MM).
    Persists to the local SQLite database and maintains legacy schedule.json.
    """
    date_clean = date.strip()
    task_clean = task.strip()

    # Parse date vs time slot if provided (e.g. "2026-03-25 08:00")
    parts = date_clean.split()
    plan_date = parts[0]
    time_slot = parts[1] if len(parts) > 1 else ""

    try:
        # Offload SQLite insert to worker thread
        await asyncio.to_thread(memory_db.add_daily_plan_entry, plan_date, task_clean, time_slot)

        # Also update legacy file safely
        def _update_legacy():
            data = load_data()
            if date_clean not in data:
                data[date_clean] = []
            if task_clean not in data[date_clean]:
                data[date_clean].append(task_clean)
            save_data(data)

        await asyncio.to_thread(_update_legacy)
        slot_str = f" at {time_slot}" if time_slot else ""
        return f"✅ Task saved for {plan_date}{slot_str}: {task_clean}"
    except Exception as e:
        logger.error(f"Error in add_schedule: {e}")
        return f"❌ Failed to save task: {e}"

@function_tool
async def get_tomorrow_schedule() -> str:
    """
    Retrieves scheduled tasks and lectures for tomorrow from the persistent SQLite database.
    """
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        plans = await asyncio.to_thread(memory_db.get_daily_plan, tomorrow)
        if not plans:
            return f"ℹ️ No tasks scheduled for tomorrow ({tomorrow})."

        formatted = []
        for p in plans:
            prefix = f"[{p['time_slot']}] " if p.get('time_slot') else "• "
            status = " [DONE]" if p.get('is_completed') else ""
            formatted.append(f"{prefix}{p['activity']}{status}")

        return f"📅 Tomorrow's Schedule ({tomorrow}):\n" + "\n".join(formatted)
    except Exception as e:
        logger.error(f"Error in get_tomorrow_schedule: {e}")
        return f"❌ Failed to retrieve tomorrow's schedule: {e}"

@function_tool
async def get_today_schedule() -> str:
    """
    Retrieves scheduled tasks, classes, and activities for today from the persistent SQLite database.
    """
    today = date.today().strftime("%Y-%m-%d")
    try:
        plans = await asyncio.to_thread(memory_db.get_daily_plan, today)
        if not plans:
            return f"ℹ️ No tasks scheduled for today ({today})."

        formatted = []
        for p in plans:
            prefix = f"[{p['time_slot']}] " if p.get('time_slot') else "• "
            status = " [DONE]" if p.get('is_completed') else ""
            formatted.append(f"{prefix}{p['activity']}{status}")

        return f"📅 Today's Schedule ({today}):\n" + "\n".join(formatted)
    except Exception as e:
        logger.error(f"Error in get_today_schedule: {e}")
        return f"❌ Failed to retrieve today's schedule: {e}"