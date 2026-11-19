import hashlib
import json
import os
import socket
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from casebook_research import upkeep_usage

URL = "https://upkeep.example.test"


def sample_message(**usage):
    fields = {
        "input_tokens": 1200,
        "output_tokens": 340,
        "cache_creation_input_tokens": 2000,
        "cache_read_input_tokens": 5000,
        "cache_creation": SimpleNamespace(ephemeral_5m_input_tokens=500, ephemeral_1h_input_tokens=1500),
        "speed": "fast",
        "inference_geo": "us",
    }
    fields.update(usage)
    return SimpleNamespace(model="claude-opus-5-5", usage=SimpleNamespace(**fields))


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return b'{"ok":true}'


class ReporterTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"UPKEEP_USAGE_URL": URL + "/", "UPKEEP_USAGE_KEY": "test-key"})
        self.env.start()
        upkeep_usage._key_cache = upkeep_usage._UNRESOLVED

    def tearDown(self):
        self.env.stop()
        upkeep_usage._key_cache = upkeep_usage._UNRESOLVED

    def test_event_carries_token_counts_and_cache_fields(self):
        event = upkeep_usage.event(sample_message())
        at = event.pop("at")
        self.assertTrue(at.endswith("Z"))
        self.assertEqual(event, {
            "model": "claude-opus-5-5",
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_creation_input_tokens": 2000,
            "cache_read_input_tokens": 5000,
            "cache_write_1h_tokens": 1500,
            "speed": "fast",
            "inference_geo": "us",
        })

    def test_event_leaves_out_missing_and_standard_fields(self):
        message = sample_message(cache_creation_input_tokens=None, cache_read_input_tokens=None,
                                 cache_creation=None, speed="standard", inference_geo=None)
        event = upkeep_usage.event(message)
        event.pop("at")
        self.assertEqual(event, {"model": "claude-opus-5-5", "input_tokens": 1200, "output_tokens": 340})

    def test_event_reads_raw_json_and_marks_batches(self):
        raw = {"id": "msg_x", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "private"}],
               "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 0,
                         "cache_creation": {"ephemeral_1h_input_tokens": 0}}}
        event = upkeep_usage.event(raw, batch=True)
        event.pop("at")
        self.assertEqual(event, {"model": "claude-opus-5-5", "input_tokens": 10, "output_tokens": 2,
                                 "cache_read_input_tokens": 0, "cache_write_1h_tokens": 0, "batch": True})
        self.assertNotIn("private", json.dumps(event))
        self.assertNotIn("msg_x", json.dumps(event))

    def test_report_posts_body_with_its_sha256(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            upkeep_usage.report(sample_message())
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, URL + "/api/usage/report")
        self.assertEqual(request.get_method(), "POST")
        self.assertLessEqual(urlopen.call_args.kwargs["timeout"], 3)
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-upkeep-key"], "test-key")
        self.assertEqual(headers["x-amz-content-sha256"], hashlib.sha256(request.data).hexdigest())
        body = json.loads(request.data)
        self.assertEqual(len(body["events"]), 1)
        self.assertEqual(body["events"][0]["cache_write_1h_tokens"], 1500)

    def test_report_does_nothing_without_url_or_key(self):
        for missing in ("UPKEEP_USAGE_URL", "UPKEEP_USAGE_KEY"):
            upkeep_usage._key_cache = upkeep_usage._UNRESOLVED
            with self.subTest(missing=missing), mock.patch.dict(os.environ, {missing: ""}), \
                    mock.patch("urllib.request.urlopen") as urlopen:
                upkeep_usage.report(sample_message())
                urlopen.assert_not_called()

    def test_report_never_raises(self):
        failures = [
            urllib.error.HTTPError(URL, 401, "Unauthorized", {}, None),
            urllib.error.HTTPError(URL, 429, "Too Many Requests", {}, None),
            urllib.error.URLError("no route"),
            socket.timeout("timed out"),
            TimeoutError(),
            RuntimeError("anything"),
        ]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch("urllib.request.urlopen", side_effect=failure), \
                    mock.patch("builtins.print") as printed:
                self.assertIsNone(upkeep_usage.report(sample_message()))
                self.assertNotIn("test-key", str(printed.call_args))

    def test_report_ignores_responses_without_usage(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            upkeep_usage.report(SimpleNamespace(model="claude-opus-5-5"))
            upkeep_usage.report(None)
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
