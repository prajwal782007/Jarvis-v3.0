import unittest
import os
from unittest.mock import patch

from Jarvis_window_CTRL import resolve_application, launch_application


class TestApplicationResolution(unittest.IsolatedAsyncioTestCase):
    def test_builtin_tools_resolved(self):
        """Verify built-in Windows applications resolve to valid commands."""
        notepad_cmd, target = resolve_application("notepad")
        self.assertEqual(notepad_cmd, "notepad")
        self.assertEqual(target, "notepad")

        calc_cmd, target = resolve_application("calculator")
        self.assertEqual(calc_cmd, "calc")

        cmd_cmd, target = resolve_application("cmd")
        self.assertEqual(cmd_cmd, "cmd")

        settings_cmd, target = resolve_application("settings")
        self.assertEqual(settings_cmd, "start ms-settings:")

    def test_no_hardcoded_user_paths(self):
        """Ensure paths for other users (like gaura) are never returned."""
        for app in ["vs code", "postman", "chrome", "vlc", "notepad"]:
            cmd, _ = resolve_application(app)
            if cmd:
                self.assertNotIn("gaura", cmd.lower())

    def test_missing_application_returns_none(self):
        """Ensure nonexistent applications return None instead of inventing paths."""
        cmd, target = resolve_application("completely_fictional_app_12345")
        self.assertIsNone(cmd)
        self.assertIsNone(target)

    async def test_launch_nonexistent_application_returns_error(self):
        """Verify launch_application gives an informative error for missing apps."""
        res = await launch_application("completely_fictional_app_12345")
        self.assertIn("could not be found", res)
        self.assertIn("completely_fictional_app_12345", res)

    def test_dynamic_lookup_via_localappdata(self):
        """Verify candidate paths inspect environment variables dynamically."""
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:\\MockAppData"}):
            with patch("os.path.exists") as mock_exists:
                def fake_exists(p):
                    return p == "C:\\MockAppData\\Programs\\Microsoft VS Code\\Code.exe"
                mock_exists.side_effect = fake_exists
                with patch("shutil.which", return_value=None):
                    cmd, target = resolve_application("vs code")
                    self.assertIsNotNone(cmd)
                    self.assertIn("C:\\MockAppData\\Programs\\Microsoft VS Code\\Code.exe", cmd)


if __name__ == "__main__":
    unittest.main()
