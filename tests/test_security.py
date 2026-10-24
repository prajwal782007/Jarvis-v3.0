import unittest
from unittest.mock import patch, MagicMock
import asyncio

from security import SecurityManager, auth_manager
from keyboard_mouse_CTRL import SafeController, safe_execute


class TestSecurityManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SecurityManager()

    def test_default_sensitive_actions_blocked(self):
        """Verify sensitive operations are blocked by default with informative message."""
        allowed, msg = self.mgr.check_authorization("file_delete", details="test_file.txt")
        self.assertFalse(allowed)
        self.assertIn("ACTION BLOCKED", msg)
        self.assertIn("file_delete", msg)

        allowed, msg = self.mgr.check_authorization("arbitrary_typing", details="test text")
        self.assertFalse(allowed)
        self.assertIn("ACTION BLOCKED", msg)

    def test_destructive_hotkey_detection(self):
        """Verify destructive hotkeys like Alt+F4 and Ctrl+W are properly identified."""
        self.assertTrue(self.mgr.is_destructive_hotkey(["alt", "f4"]))
        self.assertTrue(self.mgr.is_destructive_hotkey(["ctrl", "w"]))
        self.assertTrue(self.mgr.is_destructive_hotkey(["ctrl", "alt", "delete"]))
        self.assertTrue(self.mgr.is_destructive_hotkey(["win", "l"]))

        # Non-destructive hotkeys
        self.assertFalse(self.mgr.is_destructive_hotkey(["ctrl", "c"]))
        self.assertFalse(self.mgr.is_destructive_hotkey(["ctrl", "v"]))
        self.assertFalse(self.mgr.is_destructive_hotkey(["shift", "tab"]))

    def test_safe_actions_allowed(self):
        """Verify low-risk actions pass check_authorization."""
        allowed, msg = self.mgr.check_authorization("move_cursor")
        self.assertTrue(allowed)

        allowed, msg = self.mgr.check_authorization("control_volume")
        self.assertTrue(allowed)

    def test_temporary_authorization_grant_and_consume(self):
        """Verify temporary authorization is single-use and consumed upon action."""
        self.mgr.grant_temporary_authorization("file_delete", duration_seconds=5.0)

        # First check consumes the grant
        allowed, msg = self.mgr.check_authorization("file_delete")
        self.assertTrue(allowed)
        self.assertIn("Explicit authorization confirmed", msg)

        # Immediate second check must be blocked (single-use)
        allowed, msg = self.mgr.check_authorization("file_delete")
        self.assertFalse(allowed)
        self.assertIn("ACTION BLOCKED", msg)

    def test_expired_authorization_rejected(self):
        """Verify expired authorizations are rejected."""
        self.mgr.grant_temporary_authorization("arbitrary_typing", duration_seconds=-1.0)
        allowed, msg = self.mgr.check_authorization("arbitrary_typing")
        self.assertFalse(allowed)


class TestSafeControllerSecurity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        auth_manager.revoke_all_authorizations()
        self.controller = SafeController()

    async def test_unauthorized_typing_blocked(self):
        """Verify type_text does not press keys when unauthorized."""
        with patch.object(self.controller.keyboard, "press") as mock_press:
            res = await self.controller.type_text("rm -rf /")
            self.assertIn("ACTION BLOCKED", res)
            mock_press.assert_not_called()

    async def test_unauthorized_destructive_hotkey_blocked(self):
        """Verify press_hotkey does not press keys for Alt+F4 when unauthorized."""
        with patch.object(self.controller.keyboard, "press") as mock_press:
            res = await self.controller.press_hotkey(["alt", "f4"])
            self.assertIn("ACTION BLOCKED", res)
            mock_press.assert_not_called()

    async def test_safe_hotkey_allowed_without_block(self):
        """Verify safe hotkey executes without requiring elevation."""
        with patch.object(self.controller.keyboard, "press") as mock_press, \
             patch.object(self.controller.keyboard, "release") as mock_release:
            res = await self.controller.press_hotkey(["ctrl", "c"])
            self.assertIn("Hotkey ctrl + c pressed", res)
            self.assertEqual(mock_press.call_count, 2)
            self.assertEqual(mock_release.call_count, 2)

    async def test_no_bypass_with_old_token(self):
        """Verify there is no secret token mechanism to bypass security."""
        # SafeController no longer has an activate(token) method that accepts "my_secret_token"
        self.assertFalse(hasattr(self.controller, "activation_time"))
        with patch.object(self.controller.keyboard, "press") as mock_press:
            res = await self.controller.type_text("echo test")
            self.assertIn("ACTION BLOCKED", res)
            mock_press.assert_not_called()


if __name__ == "__main__":
    unittest.main()
