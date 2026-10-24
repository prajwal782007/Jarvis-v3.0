import unittest
import asyncio
import os
from unittest.mock import patch, MagicMock

import Jarvis_google_search
import jarvis_get_whether
import Jarvis_file_opner
import Jarvis_window_CTRL


class TestEventLoopOffloading(unittest.IsolatedAsyncioTestCase):
    async def test_google_search_uses_asyncio_to_thread(self):
        """Verify google_search offloads HTTP requests to worker threads."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": [{"title": "Test Title", "link": "http://test.com", "snippet": "Test snippet"}]}

        with patch.dict(os.environ, {"GOOGLE_SEARCH_API_KEY": "fake_key", "SEARCH_ENGINE_ID": "fake_id"}), \
             patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread, \
             patch("requests.get", return_value=mock_response) as mock_requests_get:

            result = await Jarvis_google_search.google_search("test query")
            self.assertIn("Test Title", result)
            mock_to_thread.assert_called()
            # Ensure requests.get was executed through the thread pool
            mock_requests_get.assert_called_once()

    async def test_weather_uses_asyncio_to_thread(self):
        """Verify get_weather offloads HTTP requests to worker threads."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "weather": [{"description": "clear sky"}],
            "main": {"temp": 25.0, "humidity": 50},
            "wind": {"speed": 3.5}
        }

        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": "fake_key"}), \
             patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread, \
             patch("requests.get", return_value=mock_response) as mock_requests_get:

            result = await jarvis_get_whether.get_weather("Mumbai")
            self.assertIn("Mumbai", result)
            self.assertIn("Clear Sky", result)
            mock_to_thread.assert_called()
            mock_requests_get.assert_called_once()

    async def test_index_items_uses_asyncio_to_thread(self):
        """Verify file and item indexing uses asyncio.to_thread."""
        with patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
            # Pass a non-existent or temporary directory
            items = await Jarvis_window_CTRL.index_items(["nonexistent_folder_abc"])
            self.assertIsInstance(items, list)
            mock_to_thread.assert_called()

    async def test_file_deletion_is_blocked_by_default(self):
        """Verify file deletion through folder_file or delete_item is blocked."""
        res = await Jarvis_window_CTRL.delete_item("C:\\safe\\test.txt")
        self.assertIn("ACTION BLOCKED", res)
        self.assertIn("file_delete", res)


if __name__ == "__main__":
    unittest.main()
