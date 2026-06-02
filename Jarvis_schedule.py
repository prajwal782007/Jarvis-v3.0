import json
from datetime import datetime, timedelta
from livekit.agents import function_tool

FILE = "schedule.json"

def load_data():
    try:
        with open(FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=2)

@function_tool
async def add_schedule(date: str, task: str) -> str:
    data = load_data()
    if date not in data:
        data[date] = []
    data[date].append(task)
    save_data(data)
    return f"Task saved for {date}"

@function_tool
async def get_tomorrow_schedule() -> str:
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    data = load_data()
    if tomorrow not in data:
        return "No tasks for tomorrow"
    return "\n".join(data[tomorrow])