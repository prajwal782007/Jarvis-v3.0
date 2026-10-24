import asyncio
import logging
from typing import Optional
from livekit.agents import function_tool

from memory_manager import memory_db

logger = logging.getLogger(__name__)

# -------------------------------------------------------------
# LiveKit Function Tools for Persistent Memory
# -------------------------------------------------------------

@function_tool
async def save_memory_tool(category: str, key: str, content: str, importance: int = 3) -> str:
    """
    Saves a persistent personal fact, preference, rule, or project detail.
    Example categories: 'preference', 'friend_detail', 'project_context', 'personal_rule'.
    Never stores passwords or secret keys.
    """
    try:
        res = await asyncio.to_thread(memory_db.save_memory, category, key, content, importance)
        return f"✅ Memory saved: [{res['category']}] '{res['key']}' recorded successfully."
    except ValueError as ve:
        return str(ve)
    except Exception as e:
        logger.error(f"Error in save_memory_tool: {e}")
        return f"❌ Failed to save memory: {e}"

@function_tool
async def search_memory_tool(query: str, category: str = "") -> str:
    """
    Searches long-term persistent memories by keywords or topic.
    """
    try:
        cat_filter = category.strip() if category else None
        results = await asyncio.to_thread(memory_db.search_memories, query, cat_filter)
        if not results:
            return f"ℹ️ No memories found matching '{query}'."

        formatted = [f"• [{r['category'].upper()}] {r['memory_key']}: {r['content']} (Importance: {r['importance']}/5)"
                     for r in results[:5]]
        return "🧠 Found memories:\n" + "\n".join(formatted)
    except Exception as e:
        logger.error(f"Error in search_memory_tool: {e}")
        return f"❌ Failed to search memories: {e}"

@function_tool
async def delete_memory_tool(key: str) -> str:
    """
    Explicitly deletes a stored memory by its key when requested by the user.
    """
    try:
        res = await asyncio.to_thread(memory_db.delete_memory, key)
        if res.get("deleted"):
            return f"🗑️ Memory '{key}' has been permanently deleted."
        return f"ℹ️ Memory with key '{key}' was not found."
    except Exception as e:
        logger.error(f"Error in delete_memory_tool: {e}")
        return f"❌ Failed to delete memory: {e}"

# -------------------------------------------------------------
# LiveKit Function Tools for Tasks & Assignments
# -------------------------------------------------------------

@function_tool
async def add_task_tool(title: str, due_date: str = "", category: str = "assignment",
                        priority: str = "medium", description: str = "") -> str:
    """
    Adds a new assignment, academic task, or personal responsibility with an optional due date (YYYY-MM-DD or YYYY-MM-DD HH:MM).
    """
    try:
        res = await asyncio.to_thread(
            memory_db.add_task,
            title=title,
            description=description,
            category=category,
            due_date=due_date if due_date else None,
            priority=priority
        )
        due_str = f", Due: {res['due_date']}" if res['due_date'] else ""
        return f"✅ Task added: '{res['title']}' [Category: {res['category']}, Priority: {res['priority']}{due_str}]"
    except Exception as e:
        logger.error(f"Error in add_task_tool: {e}")
        return f"❌ Failed to add task: {e}"

@function_tool
async def list_tasks_tool(status: str = "pending", category: str = "") -> str:
    """
    Lists tasks filtered by status ('pending', 'in_progress', 'completed') and optional category ('assignment', 'personal', etc.).
    """
    try:
        stat = status.strip() if status else None
        cat = category.strip() if category else None
        tasks = await asyncio.to_thread(memory_db.list_tasks, status=stat, category=cat)
        if not tasks:
            filter_desc = f" ({status})" if status else ""
            return f"ℹ️ No tasks found{filter_desc}."

        lines = []
        for t in tasks[:10]:
            due = f" | Due: {t['due_date']}" if t['due_date'] else ""
            pct = f" ({t['completion_percentage']}%)" if t['completion_percentage'] > 0 else ""
            lines.append(f"• [ID {t['id']}] {t['title']}{pct} - {t['status'].upper()}{due}")

        return "📋 Tasks list:\n" + "\n".join(lines)
    except Exception as e:
        logger.error(f"Error in list_tasks_tool: {e}")
        return f"❌ Failed to list tasks: {e}"

@function_tool
async def update_task_progress_tool(task_title_or_id: str, completion_percentage: int) -> str:
    """
    Updates the completion progress of an assignment or task (0 to 100). Automatically marks completed at 100%.
    """
    try:
        res = await asyncio.to_thread(memory_db.update_task_progress, task_title_or_id, completion_percentage)
        status_msg = "Completed! 🎉" if res['task_status'] == "completed" else f"Status: {res['task_status']}"
        return f"✅ Updated '{task_title_or_id}': Progress is now {res['completion_percentage']}% ({status_msg})"
    except KeyError:
        return f"❌ Task '{task_title_or_id}' was not found."
    except Exception as e:
        logger.error(f"Error in update_task_progress_tool: {e}")
        return f"❌ Failed to update task progress: {e}"

# -------------------------------------------------------------
# LiveKit Function Tools for Exams & Deadlines
# -------------------------------------------------------------

@function_tool
async def record_exam_or_deadline_tool(title: str, target_date: str, course_or_subject: str = "",
                                       event_type: str = "exam", topics: str = "", weightage: str = "") -> str:
    """
    Records an exam, major submission deadline, or milestone date (target_date in YYYY-MM-DD or YYYY-MM-DD HH:MM).
    """
    try:
        res = await asyncio.to_thread(
            memory_db.add_deadline_or_exam,
            title=title,
            target_date=target_date,
            event_type=event_type,
            course_or_subject=course_or_subject,
            topics=topics,
            weightage=weightage
        )
        return f"📅 Recorded {res['event_type'].upper()}: '{res['title']}' for {res['course_or_subject']} on {res['target_date']}."
    except Exception as e:
        logger.error(f"Error in record_exam_or_deadline_tool: {e}")
        return f"❌ Failed to record deadline/exam: {e}"

@function_tool
async def get_upcoming_deadlines_tool(days_ahead: int = 14) -> str:
    """
    Retrieves all upcoming exams and submission deadlines scheduled within the next N days (default 14 days).
    """
    try:
        deadlines = await asyncio.to_thread(memory_db.get_upcoming_deadlines, days_ahead)
        if not deadlines:
            return f"ℹ️ No upcoming exams or deadlines in the next {days_ahead} days."

        lines = [f"• {d['target_date']}: [{d['event_type'].upper()}] {d['title']} ({d['course_or_subject'] or 'General'})"
                 for d in deadlines]
        return f"🚨 Upcoming Deadlines & Exams (Next {days_ahead} days):\n" + "\n".join(lines)
    except Exception as e:
        logger.error(f"Error in get_upcoming_deadlines_tool: {e}")
        return f"❌ Failed to retrieve upcoming deadlines: {e}"

# -------------------------------------------------------------
# LiveKit Function Tools for Projects & People
# -------------------------------------------------------------

@function_tool
async def record_project_progress_tool(project_name: str, progress_percentage: int,
                                       notes: str = "", status: str = "active") -> str:
    """
    Records progress percentage and notes for an ongoing technical or academic project.
    """
    try:
        res = await asyncio.to_thread(memory_db.record_project_progress, project_name, progress_percentage, notes, status)
        return f"🚀 Project '{res['project']}' updated: {res['progress_percentage']}% complete (Status: {res['status']})."
    except Exception as e:
        logger.error(f"Error in record_project_progress_tool: {e}")
        return f"❌ Failed to update project progress: {e}"

@function_tool
async def remember_person_tool(name: str, role: str, project_name: str = "", notes: str = "") -> str:
    """
    Remembers a teammate, friend, or collaborator and their role in a project.
    """
    try:
        res = await asyncio.to_thread(memory_db.remember_person, name, role, project_name, notes)
        proj = f" on {res['project']}" if res['project'] else ""
        return f"👤 Remembered {res['name']} as {res['role']}{proj}."
    except Exception as e:
        logger.error(f"Error in remember_person_tool: {e}")
        return f"❌ Failed to remember person: {e}"

# -------------------------------------------------------------
# LiveKit Function Tools for Debugging Sessions
# -------------------------------------------------------------

@function_tool
async def log_debug_solution_tool(project_name: str, issue_symptom: str, resolution: str,
                                  root_cause: str = "", code_snippet: str = "") -> str:
    """
    Logs a past technical bug, its root cause, and how it was resolved for future debugging reference.
    """
    try:
        res = await asyncio.to_thread(
            memory_db.log_debugging_session,
            project_name=project_name,
            issue_symptom=issue_symptom,
            resolution=resolution,
            root_cause=root_cause,
            code_snippet=code_snippet
        )
        return f"🔧 Logged debug solution for project '{res['project']}': '{res['issue']}' resolved."
    except Exception as e:
        logger.error(f"Error in log_debug_solution_tool: {e}")
        return f"❌ Failed to log debug solution: {e}"

@function_tool
async def search_debug_solutions_tool(query: str, project_name: str = "") -> str:
    """
    Searches past debugging sessions and technical solutions to help resolve current coding errors.
    """
    try:
        p_filter = project_name.strip() if project_name else None
        results = await asyncio.to_thread(memory_db.search_debugging_resolutions, query, p_filter)
        if not results:
            return f"ℹ️ No previous debugging records found for '{query}'."

        formatted = []
        for r in results[:3]:
            cause = f"\n  Root Cause: {r['root_cause']}" if r['root_cause'] else ""
            snippet = f"\n  Snippet: {r['code_snippet']}" if r['code_snippet'] else ""
            formatted.append(f"• [{r['project_name']}] Issue: {r['issue_symptom']}{cause}\n  Resolution: {r['resolution']}{snippet}")

        return "🛠️ Past Debugging Solutions:\n" + "\n".join(formatted)
    except Exception as e:
        logger.error(f"Error in search_debug_solutions_tool: {e}")
        return f"❌ Failed to search debug solutions: {e}"
