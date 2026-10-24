import time
import logging
from typing import List, Set, Tuple, Optional

logger = logging.getLogger(__name__)

# Destructive or high-risk hotkey combinations that can close applications, lock screens, or disrupt the user
DESTRUCTIVE_HOTKEYS: List[Set[str]] = [
    {"alt", "f4"},
    {"ctrl", "w"},
    {"ctrl", "q"},
    {"ctrl", "alt", "delete"},
    {"win", "l"},
    {"win", "d"},
    {"ctrl", "shift", "esc"},
]

class SecurityManager:
    """
    Manages explicit authorization checks and safety gating for system actions.
    Eliminates silent approvals and hardcoded bypass tokens.
    """
    def __init__(self):
        # Maps action_type to an expiry timestamp (epoch seconds)
        self._authorized_grants: dict[str, float] = {}

    def is_destructive_hotkey(self, keys: List[str]) -> bool:
        """Determines whether a hotkey combination is classified as destructive."""
        normalized = {k.lower().strip() for k in keys}
        for pattern in DESTRUCTIVE_HOTKEYS:
            if pattern.issubset(normalized):
                return True
        return False

    def is_sensitive_action(self, action_type: str, **kwargs) -> bool:
        """Classifies if an action is sensitive and requires confirmation."""
        if action_type in ("file_delete", "folder_delete", "arbitrary_typing"):
            return True
        if action_type == "press_hotkey":
            keys = kwargs.get("keys", [])
            return self.is_destructive_hotkey(keys)
        return False

    def check_authorization(self, action_type: str, details: Optional[str] = None, **kwargs) -> Tuple[bool, str]:
        """
        Validates authorization for an action.
        Returns (is_allowed, message).
        Never silently approves sensitive operations.
        """
        # Clean expired grants
        now = time.time()
        expired = [act for act, exp in self._authorized_grants.items() if exp < now]
        for act in expired:
            del self._authorized_grants[act]

        if not self.is_sensitive_action(action_type, **kwargs):
            return True, "Operation is low-risk and authorized."

        # Check if an explicit grant exists
        if action_type in self._authorized_grants:
            # Single-use authorization: consume on use
            del self._authorized_grants[action_type]
            logger.info(f"Explicit authorization consumed for sensitive action: {action_type}")
            return True, f"Explicit authorization confirmed for '{action_type}'."

        # If sensitive and no grant exists:
        detail_msg = f" ({details})" if details else ""
        reason = (
            f"🛑 ACTION BLOCKED: Sensitive action '{action_type}'{detail_msg} requires explicit user confirmation. "
            f"In the current headless/voice architecture, an interactive confirmation dialog is pending implementation. "
            f"Operation safely aborted."
        )
        logger.warning(reason)
        return False, reason

    def grant_temporary_authorization(self, action_type: str, duration_seconds: float = 10.0) -> None:
        """
        Programmatically grant temporary authorization for an action.
        Used by tests or future confirmation UI prompts.
        """
        self._authorized_grants[action_type] = time.time() + duration_seconds
        logger.info(f"Temporary authorization granted for '{action_type}' for {duration_seconds}s.")

    def revoke_all_authorizations(self) -> None:
        """Revokes all pending authorization grants."""
        self._authorized_grants.clear()


# Global singleton instance
auth_manager = SecurityManager()
