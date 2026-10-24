import os
import sqlite3
import logging
import json
import re
import shutil
import hashlib
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Sensitive pattern detection to prevent storing credentials, tokens, or API keys in memory
SENSITIVE_PATTERNS = [
    re.compile(r"(livekit|api[_-]?key|secret[_-]?key|password|token|bearer|auth|gemini|openai)[\s:=]+[\"']?[A-Za-z0-9_\-\.]{8,}[\"']?", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z-_]{35}"), # Google API Key pattern
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),    # Common API token pattern
]

def get_default_db_path() -> str:
    """Returns database path in OS app data directory, allowing test override via JARVIS_DB_PATH."""
    env_path = os.environ.get("JARVIS_DB_PATH")
    if env_path:
        return env_path

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.expanduser("~")

    app_dir = os.path.join(local_app_data, "JarvisCompanion")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "jarvis_memory.db")

def is_sensitive_content(text: str) -> bool:
    """Detects whether a text payload contains authentication secrets or API keys."""
    if not text:
        return False
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return True
    return False

class MemoryManager:
    """
    Local-first, ACID-compliant persistence engine for JARVIS v3.0.
    Handles tasks, exams, projects, people, daily schedules, debugging logs, and conversation memory.
    """
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_default_db_path()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self.db_path != ":memory:":
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """Initializes tables, indexes, and schema versions safely."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Schema migration tracker
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """)

            # 2. Tasks and assignments
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'general',
                due_date TEXT,
                priority TEXT DEFAULT 'medium',
                completion_percentage INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);")

            # 3. Deadlines, exams, and milestones
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS deadlines_exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                course_or_subject TEXT,
                event_type TEXT DEFAULT 'deadline',
                target_date TEXT NOT NULL,
                weightage TEXT,
                topics_or_syllabus TEXT,
                status TEXT DEFAULT 'upcoming',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deadlines_target ON deadlines_exams(target_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_deadlines_status ON deadlines_exams(status);")

            # 4. Projects and progress
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                progress_percentage INTEGER DEFAULT 0,
                repo_path TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);")

            # 5. People and project affiliations
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT,
                project_name TEXT,
                affiliation TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);")

            # 6. Daily schedule and plans
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_date TEXT NOT NULL,
                time_slot TEXT,
                activity TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                rescheduled_from TEXT,
                source_file TEXT,
                raw_fingerprint TEXT UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_plans_date ON daily_plans(plan_date);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_plans_fingerprint ON daily_plans(raw_fingerprint);")

            # 7. Long-term conversation memories (durable personal facts & rules)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                memory_key TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 3,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON conversation_memories(category);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON conversation_memories(memory_key);")

            # 8. Debugging sessions and solutions
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS debugging_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                issue_symptom TEXT NOT NULL,
                root_cause TEXT,
                resolution TEXT NOT NULL,
                code_snippet TEXT,
                created_at TEXT NOT NULL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_debugging_project ON debugging_sessions(project_name);")

            # Record baseline schema version 1
            cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?)",
                           (datetime.now(timezone.utc).isoformat(),))
            conn.commit()

    # -------------------------------------------------------------
    # Memory Operations
    # -------------------------------------------------------------
    def save_memory(self, category: str, key: str, content: str, importance: int = 3) -> Dict[str, Any]:
        """Saves or updates a durable memory fact. Rejects secrets."""
        if is_sensitive_content(content) or is_sensitive_content(key):
            raise ValueError("🛑 Security Violation: Detected credentials or API keys. Memories must not store secrets.")

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO conversation_memories (category, memory_key, content, importance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_key) DO UPDATE SET
                category=excluded.category,
                content=excluded.content,
                importance=excluded.importance,
                updated_at=excluded.updated_at;
            """, (category.strip().lower(), key.strip().lower(), content.strip(), importance, now, now))
            conn.commit()
            return {"status": "success", "key": key, "category": category, "importance": importance}

    def retrieve_memory(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single memory by its unique key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM conversation_memories WHERE memory_key = ?", (key.strip().lower(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def search_memories(self, query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches memories by text matching key or content."""
        q = f"%{query.strip().lower()}%"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("""
                SELECT * FROM conversation_memories 
                WHERE category = ? AND (memory_key LIKE ? OR content LIKE ?)
                ORDER BY importance DESC, updated_at DESC
                """, (category.strip().lower(), q, q))
            else:
                cursor.execute("""
                SELECT * FROM conversation_memories 
                WHERE memory_key LIKE ? OR content LIKE ?
                ORDER BY importance DESC, updated_at DESC
                """, (q, q))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def update_memory(self, key: str, content: str, importance: Optional[int] = None) -> Dict[str, Any]:
        """Updates an existing memory's content or importance."""
        if is_sensitive_content(content):
            raise ValueError("🛑 Security Violation: Detected credentials or API keys. Memories must not store secrets.")

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if importance is not None:
                cursor.execute("""
                UPDATE conversation_memories 
                SET content = ?, importance = ?, updated_at = ?
                WHERE memory_key = ?
                """, (content.strip(), importance, now, key.strip().lower()))
            else:
                cursor.execute("""
                UPDATE conversation_memories 
                SET content = ?, updated_at = ?
                WHERE memory_key = ?
                """, (content.strip(), now, key.strip().lower()))
            if cursor.rowcount == 0:
                raise KeyError(f"Memory with key '{key}' not found.")
            conn.commit()
            return {"status": "success", "key": key}

    def delete_memory(self, key_or_id: str) -> Dict[str, Any]:
        """Explicitly deletes a memory record by key or ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if key_or_id.isdigit():
                cursor.execute("DELETE FROM conversation_memories WHERE id = ?", (int(key_or_id),))
            else:
                cursor.execute("DELETE FROM conversation_memories WHERE memory_key = ?", (key_or_id.strip().lower(),))
            deleted = cursor.rowcount > 0
            conn.commit()
            return {"status": "success" if deleted else "not_found", "deleted": deleted, "target": key_or_id}

    # -------------------------------------------------------------
    # Task and Assignment Management
    # -------------------------------------------------------------
    def add_task(self, title: str, description: str = "", category: str = "assignment",
                 due_date: Optional[str] = None, priority: str = "medium") -> Dict[str, Any]:
        """Adds a new task or assignment."""
        now = datetime.now(timezone.utc).isoformat()
        norm_due = due_date.strip() if due_date else None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO tasks (title, description, category, due_date, priority, completion_percentage, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, 'pending', ?, ?)
            """, (title.strip(), description.strip(), category.strip().lower(), norm_due, priority.strip().lower(), now, now))
            task_id = cursor.lastrowid
            conn.commit()
            return {
                "id": task_id, "title": title, "category": category,
                "due_date": norm_due, "priority": priority, "status": "pending", "completion_percentage": 0
            }

    def list_tasks(self, status: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists tasks filtered by status and/or category."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM tasks WHERE 1=1"
            params = []
            if status:
                query += " AND status = ?"
                params.append(status.strip().lower())
            if category:
                query += " AND category = ?"
                params.append(category.strip().lower())
            query += " ORDER BY CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, due_date ASC, priority DESC"
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def update_task_progress(self, task_id_or_title: str, completion_percentage: int,
                             status: Optional[str] = None) -> Dict[str, Any]:
        """Updates task completion percentage (0-100) and status."""
        pct = max(0, min(100, completion_percentage))
        now = datetime.now(timezone.utc).isoformat()

        # Infer status if not explicitly given
        if not status:
            if pct == 100:
                status = "completed"
            elif pct > 0:
                status = "in_progress"
            else:
                status = "pending"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if task_id_or_title.isdigit():
                cursor.execute("""
                UPDATE tasks SET completion_percentage = ?, status = ?, updated_at = ?
                WHERE id = ?
                """, (pct, status.strip().lower(), now, int(task_id_or_title)))
            else:
                cursor.execute("""
                UPDATE tasks SET completion_percentage = ?, status = ?, updated_at = ?
                WHERE LOWER(title) = ?
                """, (pct, status.strip().lower(), now, task_id_or_title.strip().lower()))

            if cursor.rowcount == 0:
                raise KeyError(f"Task '{task_id_or_title}' not found.")
            conn.commit()
            return {"status": "success", "task": task_id_or_title, "completion_percentage": pct, "task_status": status}

    def complete_task(self, task_id_or_title: str) -> Dict[str, Any]:
        """Shortcut to mark a task 100% complete."""
        return self.update_task_progress(task_id_or_title, 100, status="completed")

    # -------------------------------------------------------------
    # Deadlines, Exams & Milestones
    # -------------------------------------------------------------
    def add_deadline_or_exam(self, title: str, target_date: str, event_type: str = "deadline",
                             course_or_subject: str = "", topics: str = "", weightage: str = "") -> Dict[str, Any]:
        """Records an exam, submission date, or milestone."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO deadlines_exams (title, course_or_subject, event_type, target_date, weightage, topics_or_syllabus, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'upcoming', ?, ?)
            """, (title.strip(), course_or_subject.strip(), event_type.strip().lower(), target_date.strip(),
                  weightage.strip(), topics.strip(), now, now))
            row_id = cursor.lastrowid
            conn.commit()
            return {
                "id": row_id, "title": title, "target_date": target_date,
                "event_type": event_type, "course_or_subject": course_or_subject
            }

    def get_upcoming_deadlines(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """Retrieves deadlines and exams within the specified window."""
        today = date.today().isoformat()
        end_day = (date.today() + timedelta(days=days_ahead)).isoformat() + " 23:59:59"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM deadlines_exams
            WHERE target_date >= ? AND target_date <= ? AND status = 'upcoming'
            ORDER BY target_date ASC
            """, (today, end_day))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # Daily Schedule / Plans
    # -------------------------------------------------------------
    def add_daily_plan_entry(self, plan_date: str, activity: str, time_slot: str = "") -> Dict[str, Any]:
        """Adds an activity to the daily schedule with idempotency fingerprinting."""
        now = datetime.now(timezone.utc).isoformat()
        norm_date = plan_date.strip()
        norm_slot = time_slot.strip()
        norm_act = activity.strip()
        fingerprint = hashlib.sha256(f"{norm_date}_{norm_slot}_{norm_act}".encode("utf-8")).hexdigest()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO daily_plans (plan_date, time_slot, activity, is_completed, raw_fingerprint, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?, ?)
            """, (norm_date, norm_slot, norm_act, fingerprint, now, now))
            row_id = cursor.lastrowid
            conn.commit()
            return {"id": row_id, "date": norm_date, "time_slot": norm_slot, "activity": norm_act}

    def get_daily_plan(self, plan_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves daily activities for a given date (defaults to today)."""
        target = plan_date.strip() if plan_date else date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Match date prefix to handle both YYYY-MM-DD and timestamped keys
            cursor.execute("""
            SELECT * FROM daily_plans
            WHERE plan_date LIKE ? OR plan_date = ?
            ORDER BY CASE WHEN time_slot IS NULL OR time_slot = '' THEN 1 ELSE 0 END, time_slot ASC, id ASC
            """, (f"{target}%", target))
            return [dict(r) for r in cursor.fetchall()]

    def mark_daily_plan_completed(self, plan_id_or_activity: str, plan_date: Optional[str] = None) -> Dict[str, Any]:
        """Marks a daily plan activity as completed."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if plan_id_or_activity.isdigit():
                cursor.execute("""
                UPDATE daily_plans SET is_completed = 1, updated_at = ? WHERE id = ?
                """, (now, int(plan_id_or_activity)))
            else:
                target_date = plan_date.strip() if plan_date else date.today().isoformat()
                cursor.execute("""
                UPDATE daily_plans SET is_completed = 1, updated_at = ? 
                WHERE LOWER(activity) LIKE ? AND plan_date LIKE ?
                """, (now, f"%{plan_id_or_activity.strip().lower()}%", f"{target_date}%"))

            updated = cursor.rowcount > 0
            conn.commit()
            return {"status": "success" if updated else "not_found", "completed": updated}

    # -------------------------------------------------------------
    # Projects & People
    # -------------------------------------------------------------
    def record_project_progress(self, name: str, progress_percentage: int,
                                notes: str = "", status: str = "active", description: str = "") -> Dict[str, Any]:
        """Records or updates a project's status and progress percentage."""
        pct = max(0, min(100, progress_percentage))
        now = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO projects (name, description, status, progress_percentage, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = CASE WHEN excluded.description != '' THEN excluded.description ELSE projects.description END,
                status = excluded.status,
                progress_percentage = excluded.progress_percentage,
                notes = CASE WHEN excluded.notes != '' THEN excluded.notes ELSE projects.notes END,
                updated_at = excluded.updated_at;
            """, (name.strip(), description.strip(), status.strip().lower(), pct, notes.strip(), now, now))
            conn.commit()
            return {"project": name, "progress_percentage": pct, "status": status}

    def get_project_history(self, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves history and details of projects."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if name:
                cursor.execute("SELECT * FROM projects WHERE LOWER(name) = ?", (name.strip().lower(),))
            else:
                cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    def remember_person(self, name: str, role: str, project_name: str = "",
                        notes: str = "", affiliation: str = "") -> Dict[str, Any]:
        """Stores information about a friend, teammate, or collaborator."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO people (name, role, project_name, affiliation, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name.strip(), role.strip(), project_name.strip(), affiliation.strip(), notes.strip(), now, now))
            person_id = cursor.lastrowid
            conn.commit()
            return {"id": person_id, "name": name, "role": role, "project": project_name}

    def get_person_details(self, name: str) -> List[Dict[str, Any]]:
        """Retrieves details of a person or teammate."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM people WHERE LOWER(name) LIKE ? ORDER BY updated_at DESC",
                           (f"%{name.strip().lower()}%",))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # Debugging Sessions
    # -------------------------------------------------------------
    def log_debugging_session(self, project_name: str, issue_symptom: str, resolution: str,
                              root_cause: str = "", code_snippet: str = "") -> Dict[str, Any]:
        """Logs a technical problem and how it was solved for future recall."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO debugging_sessions (project_name, issue_symptom, root_cause, resolution, code_snippet, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (project_name.strip(), issue_symptom.strip(), root_cause.strip(), resolution.strip(), code_snippet.strip(), now))
            session_id = cursor.lastrowid
            conn.commit()
            return {"id": session_id, "project": project_name, "issue": issue_symptom, "status": "resolved"}

    def search_debugging_resolutions(self, query: str, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches past debugging sessions by query keywords."""
        q = f"%{query.strip().lower()}%"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if project_name:
                cursor.execute("""
                SELECT * FROM debugging_sessions
                WHERE LOWER(project_name) = ? AND (LOWER(issue_symptom) LIKE ? OR LOWER(resolution) LIKE ? OR LOWER(root_cause) LIKE ?)
                ORDER BY created_at DESC
                """, (project_name.strip().lower(), q, q, q))
            else:
                cursor.execute("""
                SELECT * FROM debugging_sessions
                WHERE LOWER(issue_symptom) LIKE ? OR LOWER(resolution) LIKE ? OR LOWER(root_cause) LIKE ? OR LOWER(project_name) LIKE ?
                ORDER BY created_at DESC
                """, (q, q, q, q))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # Schedule JSON Migration
    # -------------------------------------------------------------
    def migrate_schedule_json(self, schedule_file: str = "schedule.json") -> Dict[str, Any]:
        """
        Safely imports existing schedule.json entries into the SQLite daily_plans table.
        Backs up schedule.json to schedule.json.bak before any processing.
        Never deletes the original file. Fully idempotent using entry fingerprints.
        """
        if not os.path.exists(schedule_file):
            return {"status": "file_not_found", "message": f"'{schedule_file}' does not exist.", "migrated": 0, "skipped": 0}

        backup_file = f"{schedule_file}.bak"
        if not os.path.exists(backup_file):
            shutil.copy2(schedule_file, backup_file)
            logger.info(f"Backed up {schedule_file} to {backup_file}")

        try:
            with open(schedule_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {schedule_file}: {e}")
            return {"status": "error", "message": str(e), "migrated": 0, "skipped": 0}

        now = datetime.now(timezone.utc).isoformat()
        migrated_count = 0
        skipped_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for key, activities in raw_data.items():
                if not isinstance(activities, list):
                    continue

                # Parse date-only ("2026-03-25") vs date-time ("2026-03-25 08:00")
                key_parts = key.strip().split()
                plan_date = key_parts[0]
                time_slot = key_parts[1] if len(key_parts) > 1 else ""

                for act in activities:
                    if not isinstance(act, str) or not act.strip():
                        continue
                    act_clean = act.strip()
                    fingerprint = hashlib.sha256(f"{plan_date}_{time_slot}_{act_clean}".encode("utf-8")).hexdigest()

                    cursor.execute("""
                    INSERT OR IGNORE INTO daily_plans (plan_date, time_slot, activity, is_completed, source_file, raw_fingerprint, created_at, updated_at)
                    VALUES (?, ?, ?, 0, 'schedule.json', ?, ?, ?)
                    """, (plan_date, time_slot, act_clean, fingerprint, now, now))

                    if cursor.rowcount > 0:
                        migrated_count += 1
                    else:
                        skipped_count += 1
            conn.commit()

        logger.info(f"Schedule migration completed: {migrated_count} inserted, {skipped_count} skipped/already present.")
        return {
            "status": "success",
            "migrated": migrated_count,
            "skipped": skipped_count,
            "backup_created": os.path.exists(backup_file),
            "backup_file": backup_file
        }


# Global instance
memory_db = MemoryManager()
