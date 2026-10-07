import http.client
import unittest
import urllib.error
from unittest.mock import MagicMock, call, patch

from scripts import build_metadata as meta


class FetchTests(unittest.TestCase):
    def test_incomplete_body_is_discarded_and_download_retried(self):
        url = "https://example.org/library.jar"
        truncated = MagicMock()
        truncated.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"partial", 42)
        complete = MagicMock()
        complete.__enter__.return_value.read.return_value = b"complete artifact"
        with (patch.object(meta.urllib.request, "urlopen", side_effect=[truncated, complete]) as open_url,
              patch.object(meta.time, "sleep") as sleep,
              self.assertLogs(level="WARNING") as logs):
            self.assertEqual(meta.fetch(url), b"complete artifact")
        self.assertEqual([c.args[0].full_url for c in open_url.call_args_list], [url, url])
        truncated.__exit__.assert_called_once()
        complete.__exit__.assert_called_once()
        sleep.assert_called_once_with(1)
        self.assertIn(url, logs.output[0])
        self.assertIn("IncompleteRead", logs.output[0])

    def test_retries_are_bounded_and_final_error_identifies_url(self):
        url = "https://example.org/library.jar"
        response = MagicMock()
        error = http.client.IncompleteRead(b"partial", 42)
        response.__enter__.return_value.read.side_effect = error
        with (patch.object(meta.urllib.request, "urlopen", return_value=response) as open_url,
              patch.object(meta.time, "sleep") as sleep,
              self.assertLogs(level="WARNING"),
              self.assertRaises(http.client.IncompleteRead) as raised):
            meta.fetch(url)
        self.assertIs(raised.exception, error)
        self.assertIn(f"Failed to fetch {url} after 4 attempts", error.__notes__)
        self.assertEqual(open_url.call_count, 4)
        self.assertEqual(response.__exit__.call_count, 4)
        self.assertEqual(sleep.call_args_list, [call(1), call(2), call(4)])

    def test_connection_errors_and_timeouts_still_retry(self):
        for error in (urllib.error.URLError("connection failed"), TimeoutError("timed out")):
            with self.subTest(error=type(error).__name__):
                response = MagicMock()
                response.__enter__.return_value.read.return_value = b"complete"
                with (patch.object(meta.urllib.request, "urlopen", side_effect=[error, response]),
                      patch.object(meta.time, "sleep"), self.assertLogs(level="WARNING")):
                    self.assertEqual(meta.fetch("https://example.org/library.jar"), b"complete")
