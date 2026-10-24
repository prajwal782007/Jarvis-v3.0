from dotenv import load_dotenv
from jarvis_face import jarvis_speak, start_jarvis_face
import threading

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import google, noise_cancellation

from Jarvis_prompts import behavior_prompts, Reply_prompts
from Jarvis_google_search import google_search, get_current_datetime
from jarvis_get_whether import get_weather
from Jarvis_window_CTRL import launch_application, close, folder_file
from Jarvis_file_opner import Play_file
from Jarvis_schedule import add_schedule, get_tomorrow_schedule, get_today_schedule
from memory_tools import (
    save_memory_tool, search_memory_tool, delete_memory_tool,
    add_task_tool, list_tasks_tool, update_task_progress_tool,
    record_exam_or_deadline_tool, get_upcoming_deadlines_tool,
    record_project_progress_tool, remember_person_tool,
    log_debug_solution_tool, search_debug_solutions_tool
)
from keyboard_mouse_CTRL import (
    move_cursor_tool, mouse_click_tool, scroll_cursor_tool,
    type_text_tool, press_key_tool, swipe_gesture_tool,
    press_hotkey_tool, control_volume_tool
)

load_dotenv()


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=behavior_prompts,
            tools=[
                google_search,
                get_current_datetime,
                get_weather,
                launch_application,
                close,
                folder_file,
                Play_file,
                add_schedule,
                get_tomorrow_schedule,
                get_today_schedule,
                save_memory_tool,
                search_memory_tool,
                delete_memory_tool,
                add_task_tool,
                list_tasks_tool,
                update_task_progress_tool,
                record_exam_or_deadline_tool,
                get_upcoming_deadlines_tool,
                record_project_progress_tool,
                remember_person_tool,
                log_debug_solution_tool,
                search_debug_solutions_tool,
                move_cursor_tool,
                mouse_click_tool,
                scroll_cursor_tool,
                type_text_tool,
                press_key_tool,
                press_hotkey_tool,
                control_volume_tool,
                swipe_gesture_tool,
            ]
        )

    async def on_text_message(self, message: str):
        response = await self.generate_reply(message)
        text = getattr(response, "text", str(response))
        await self.speak(text)


async def entrypoint(ctx: agents.JobContext):

    session = AgentSession(
        llm=google.beta.realtime.RealtimeModel(
            voice="Charon"
        )
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            video_enabled=True
        ),
    )

    await ctx.connect()

    # Agent is now ready to handle messages


if __name__ == "__main__":
    print("🤖 Starting Jarvis Agent...")
    print("📡 Connecting to LiveKit...")
    
    # Start face UI in background thread so main process can continue
    face_thread = threading.Thread(target=start_jarvis_face, daemon=True)
    face_thread.start()

    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except KeyboardInterrupt:
        print("\n🛑 Jarvis stopped.")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")