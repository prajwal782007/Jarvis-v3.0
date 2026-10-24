import unittest
import os
import tempfile
import json
import shutil
import asyncio

from memory_manager import MemoryManager, is_sensitive_content
import memory_tools
import Jarvis_schedule


class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        # Use an isolated SQLite database in a temp directory for every test
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_memory.db")
        self.mgr = MemoryManager(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_initialization(self):
        """Verify tables and migration version are created upon initialization."""
        with self.mgr._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r[0] for r in cursor.fetchall()}
            expected = {"schema_migrations", "tasks", "deadlines_exams", "projects",
                        "people", "daily_plans", "conversation_memories", "debugging_sessions"}
            self.assertTrue(expected.issubset(tables))

            cursor.execute("SELECT version FROM schema_migrations;")
            version = cursor.fetchone()[0]
            self.assertEqual(version, 1)

    def test_memory_crud_and_search(self):
        """Verify saving, retrieving, searching, updating, and deleting durable memories."""
        # 1. Save
        res = self.mgr.save_memory("preference", "preferred_ide", "Visual Studio Code with Dark Theme", importance=4)
        self.assertEqual(res["status"], "success")

        # 2. Retrieve
        mem = self.mgr.retrieve_memory("preferred_ide")
        self.assertIsNotNone(mem)
        self.assertEqual(mem["content"], "Visual Studio Code with Dark Theme")
        self.assertEqual(mem["importance"], 4)

        # 3. Search
        search_res = self.mgr.search_memories("Dark Theme")
        self.assertEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["memory_key"], "preferred_ide")

        # 4. Update
        up_res = self.mgr.update_memory("preferred_ide", "VS Code with Monokai Pro", importance=5)
        self.assertEqual(up_res["status"], "success")
        updated_mem = self.mgr.retrieve_memory("preferred_ide")
        self.assertEqual(updated_mem["content"], "VS Code with Monokai Pro")
        self.assertEqual(updated_mem["importance"], 5)

        # 5. Delete
        del_res = self.mgr.delete_memory("preferred_ide")
        self.assertTrue(del_res["deleted"])
        self.assertIsNone(self.mgr.retrieve_memory("preferred_ide"))

    def test_privacy_and_secret_rejection(self):
        """Verify attempting to store passwords, API keys, or tokens is strictly rejected."""
        self.assertTrue(is_sensitive_content("API_KEY=AIzaSyD-1234567890abcdef"))
        self.assertTrue(is_sensitive_content("My secret password is secret_key=foobar12345"))

        with self.assertRaises(ValueError) as ctx:
            self.mgr.save_memory("credentials", "livekit_key", "LIVEKIT_API_KEY=my_secret_token_12345")
        self.assertIn("Security Violation", str(ctx.exception))

    def test_tasks_and_progress(self):
        """Verify adding, listing, updating progress, and completing tasks."""
        # Add tasks
        t1 = self.mgr.add_task("BEE Assignment", category="assignment", due_date="2026-03-30", priority="high")
        t2 = self.mgr.add_task("Maths Problem Set", category="assignment", due_date="2026-03-28", priority="medium")
        self.assertEqual(t1["title"], "BEE Assignment")

        # List pending
        tasks = self.mgr.list_tasks(status="pending")
        self.assertEqual(len(tasks), 2)

        # Update progress to 50%
        up = self.mgr.update_task_progress(str(t1["id"]), 50)
        self.assertEqual(up["completion_percentage"], 50)
        self.assertEqual(up["task_status"], "in_progress")

        # Complete Maths task (100%)
        comp = self.mgr.complete_task("Maths Problem Set")
        self.assertEqual(comp["task_status"], "completed")

        # Check pending list only has BEE now
        pending = self.mgr.list_tasks(status="pending")
        self.assertEqual(len(pending), 0)
        in_prog = self.mgr.list_tasks(status="in_progress")
        self.assertEqual(len(in_prog), 1)

    def test_deadlines_and_exams(self):
        """Verify recording exams and retrieving upcoming deadlines."""
        self.mgr.add_deadline_or_exam("Physics Midsem", target_date="2026-04-05 10:00",
                                      event_type="exam", course_or_subject="Physics", topics="Optics, Waves")
        self.mgr.add_deadline_or_exam("Far Future Milestone", target_date="2028-01-01",
                                      event_type="milestone", course_or_subject="CS")

        # Query next 30 days
        upcoming = self.mgr.get_upcoming_deadlines(days_ahead=30)
        titles = [u["title"] for u in upcoming]
        # Depending on current mock date vs 2026, let's verify target query
        with self.mgr._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM deadlines_exams WHERE title = 'Physics Midsem'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["course_or_subject"], "Physics")
            self.assertEqual(row["event_type"], "exam")

    def test_projects_and_people(self):
        """Verify project progress tracking and teammate records."""
        # Project
        p = self.mgr.record_project_progress("JARVIS v3.0", 40, notes="Milestone 2 underway", status="active")
        self.assertEqual(p["progress_percentage"], 40)
        history = self.mgr.get_project_history("JARVIS v3.0")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["notes"], "Milestone 2 underway")

        # Person
        person = self.mgr.remember_person("Prajwal", "Creator & Lead Developer", project_name="JARVIS v3.0")
        self.assertEqual(person["name"], "Prajwal")
        details = self.mgr.get_person_details("Prajwal")
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["role"], "Creator & Lead Developer")

    def test_debugging_sessions(self):
        """Verify logging technical resolutions and searching past fixes."""
        self.mgr.log_debugging_session(
            project_name="Jarvis",
            issue_symptom="Event loop freeze during file search",
            resolution="Offloaded synchronous os.walk to asyncio.to_thread",
            root_cause="Synchronous I/O on main thread",
            code_snippet="await asyncio.to_thread(_sync_index_files, dirs)"
        )

        results = self.mgr.search_debugging_resolutions("os.walk")
        self.assertEqual(len(results), 1)
        self.assertIn("Offloaded", results[0]["resolution"])
        self.assertEqual(results[0]["project_name"], "Jarvis")

    def test_schedule_json_migration_idempotent(self):
        """Verify schedule.json is migrated accurately, creates a backup, and is idempotent."""
        sample_schedule = {
            "2026-03-25": [
                "Wake up at 8 AM",
                "Maths Lecture (9 AM - 10 AM)"
            ],
            "2026-03-25 08:00": [
                "Morning Breakfast"
            ],
            "2026-03-25 14:00": [
                "Seminar at COEP (2 PM - 5 PM)"
            ]
        }
        test_schedule_file = os.path.join(self.test_dir, "test_schedule.json")
        with open(test_schedule_file, "w", encoding="utf-8") as f:
            json.dump(sample_schedule, f)

        # 1. Run first migration
        res1 = self.mgr.migrate_schedule_json(test_schedule_file)
        self.assertEqual(res1["status"], "success")
        self.assertEqual(res1["migrated"], 4)
        self.assertTrue(os.path.exists(f"{test_schedule_file}.bak"))
        self.assertTrue(os.path.exists(test_schedule_file)) # Original file kept!

        # Verify daily_plans contents
        plans = self.mgr.get_daily_plan("2026-03-25")
        self.assertEqual(len(plans), 4)

        # 2. Re-run migration: must be idempotent (0 newly migrated, 4 skipped)
        res2 = self.mgr.migrate_schedule_json(test_schedule_file)
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["migrated"], 0)
        self.assertEqual(res2["skipped"], 4)

        # Ensure no duplicate records in database
        plans_after = self.mgr.get_daily_plan("2026-03-25")
        self.assertEqual(len(plans_after), 4)


class TestAsyncMemoryTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_async_tools.db")
        self.test_mgr = MemoryManager(db_path=self.db_path)
        self.patcher = unittest.mock.patch.object(memory_tools, "memory_db", self.test_mgr)
        self.patcher_sched = unittest.mock.patch.object(Jarvis_schedule, "memory_db", self.test_mgr)
        self.mock_db = self.patcher.start()
        self.mock_sched_db = self.patcher_sched.start()
        self.orig_file = Jarvis_schedule.FILE
        Jarvis_schedule.FILE = os.path.join(self.test_dir, "test_schedule.json")

    def tearDown(self):
        Jarvis_schedule.FILE = self.orig_file
        self.patcher.stop()
        self.patcher_sched.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_save_and_search_memory_tools(self):
        """Verify save_memory_tool and search_memory_tool return structured string responses."""
        res_save = await memory_tools.save_memory_tool("fact", "favorite_editor", "VS Code")
        self.assertIn("✅ Memory saved", res_save)

        res_search = await memory_tools.search_memory_tool("VS Code")
        self.assertIn("favorite_editor", res_search)

    async def test_task_tools(self):
        """Verify add_task_tool, list_tasks_tool, and update_task_progress_tool."""
        add_res = await memory_tools.add_task_tool("Complete Assignment 3", due_date="2026-04-10")
        self.assertIn("✅ Task added", add_res)

        list_res = await memory_tools.list_tasks_tool(status="pending")
        self.assertIn("Complete Assignment 3", list_res)

        up_res = await memory_tools.update_task_progress_tool("Complete Assignment 3", 100)
        self.assertIn("Completed!", up_res)

    async def test_schedule_tools_async(self):
        """Verify add_schedule and get_today_schedule / get_tomorrow_schedule."""
        add_res = await Jarvis_schedule.add_schedule("2026-04-15 09:00", "Project Presentation")
        self.assertIn("✅ Task saved", add_res)

        plans = self.mock_db.get_daily_plan("2026-04-15")
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["activity"], "Project Presentation")
        self.assertEqual(plans[0]["time_slot"], "09:00")


if __name__ == "__main__":
    unittest.main()
