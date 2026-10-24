import unittest
import builtins
import agent
import Jarvis_window_CTRL


class TestNamespaceAndImports(unittest.TestCase):
    def test_open_builtin_not_shadowed_in_agent(self):
        """Ensure Python's built-in open() is not overwritten in agent module namespace."""
        # agent module should not define or shadow 'open' in its own namespace
        self.assertNotIn("open", agent.__dict__)
        # Any code in agent resolving open resolves to the python builtin
        agent_builtins = agent.__builtins__
        if isinstance(agent_builtins, dict):
            self.assertIs(agent_builtins["open"], builtins.open)
        else:
            self.assertIs(getattr(agent_builtins, "open"), builtins.open)

    def test_launch_application_in_assistant_tools(self):
        """Verify Assistant registers launch_application."""
        assistant = agent.Assistant()
        tool_names = [getattr(t, "__name__", str(t)) for t in assistant._tools]
        self.assertIn("launch_application", tool_names)
        self.assertNotIn("open", tool_names)

    def test_requirements_contains_pygetwindow(self):
        """Verify pygetwindow is present in requirements.txt."""
        with open("requirements.txt", "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pygetwindow", content)


if __name__ == "__main__":
    unittest.main()
