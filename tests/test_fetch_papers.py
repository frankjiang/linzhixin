import io
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_papers  # noqa: E402


ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""


class FakeResponse:
    def __init__(self, text=ATOM_XML):
        self._body = text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


class FetchArxivTests(unittest.TestCase):
    def setUp(self):
        fetch_papers._last_arxiv_request_at = None

    def test_repeated_query_uses_current_arxiv_day_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with (
                mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", cache_dir),
                mock.patch.object(fetch_papers, "_arxiv_day", return_value="2026-08-12"),
                mock.patch.object(fetch_papers, "_open_arxiv", return_value=FakeResponse()) as open_arxiv,
                mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
            ):
                first = fetch_papers.fetch_arxiv("world model", max_results=100)
                second = fetch_papers.fetch_arxiv("world model", max_results=100)

            self.assertEqual(ATOM_XML, first)
            self.assertEqual(first, second)
            self.assertEqual(1, open_arxiv.call_count)

    def test_rate_limiter_applies_between_all_requests(self):
        fetch_papers._last_arxiv_request_at = 100.0
        with (
            mock.patch.object(fetch_papers.time, "monotonic", side_effect=[101.0, 104.1]),
            mock.patch.object(fetch_papers.time, "sleep") as sleep,
        ):
            fetch_papers._wait_for_arxiv_slot()

        sleep.assert_called_once_with(mock.ANY)
        self.assertAlmostEqual(2.1, sleep.call_args.args[0], places=5)
        self.assertEqual(104.1, fetch_papers._last_arxiv_request_at)

    def test_429_falls_back_to_last_successful_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with (
                mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", cache_dir),
                mock.patch.object(fetch_papers, "_arxiv_day", return_value="2026-08-11"),
                mock.patch.object(fetch_papers, "_open_arxiv", return_value=FakeResponse()),
                mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
            ):
                fetch_papers.fetch_arxiv("world model", max_results=100)

            error = urllib.error.HTTPError(
                "https://export.arxiv.org/api/query",
                429,
                "Too Many Requests",
                {"Retry-After": "0"},
                io.BytesIO(),
            )
            with (
                mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", cache_dir),
                mock.patch.object(fetch_papers, "_arxiv_day", return_value="2026-08-12"),
                mock.patch.object(fetch_papers, "_open_arxiv", side_effect=error) as open_arxiv,
                mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
                mock.patch.object(fetch_papers.time, "sleep"),
            ):
                result = fetch_papers.fetch_arxiv("world model", max_results=100)

            self.assertEqual(ATOM_XML, result)
            self.assertEqual(3, open_arxiv.call_count)


if __name__ == "__main__":
    unittest.main()
