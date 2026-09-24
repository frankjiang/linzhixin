import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_papers  # noqa: E402


ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""


def atom_page(count, prefix, *, excluded_last=False, days_old=0):
    published = (datetime.now() - timedelta(days=days_old)).isoformat() + "Z"
    entries = []
    for i in range(count):
        category = "cs.CL" if excluded_last and i == count - 1 else "cs.CV"
        entries.append(f"""<entry>
<id>https://arxiv.org/abs/{prefix}-{i}</id>
<published>{published}</published><title>Video world model</title>
<summary>Action-conditioned video prediction.</summary>
<author><name>Author</name></author><category term="{category}"/>
</entry>""")
    return '<feed xmlns="http://www.w3.org/2005/Atom">' + ''.join(entries) + '</feed>'


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

    def test_429_with_stale_cache_fails_and_preserves_cache(self):
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
                mock.patch.object(fetch_papers, "ARXIV_MAX_ATTEMPTS", 3),
                mock.patch.object(fetch_papers.time, "sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "429.*2026-08-11") as raised:
                    fetch_papers.fetch_arxiv("world model", max_results=100)

            self.assertIs(error, raised.exception.__cause__)
            self.assertEqual(3, open_arxiv.call_count)
            cached = next(cache_dir.glob('*.xml'))
            self.assertEqual(ATOM_XML, cached.read_text())
            self.assertEqual('2026-08-11', cached.with_suffix('.day').read_text().strip())

    def test_transient_406_retries_with_backoff_then_uses_fresh_response(self):
        error = urllib.error.HTTPError(
            "https://export.arxiv.org/api/query", 406, "Not Acceptable", {}, io.BytesIO()
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "_open_arxiv", side_effect=[error, FakeResponse()]) as open_arxiv,
            mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
            mock.patch.object(fetch_papers.time, "sleep") as sleep,
        ):
            result = fetch_papers.fetch_arxiv("world model", deadline=fetch_papers.time.monotonic() + 60)

        self.assertEqual(ATOM_XML, result)
        self.assertEqual(2, open_arxiv.call_count)
        sleep.assert_called_once_with(30)

    def test_permanent_http_error_does_not_wait_for_an_hour(self):
        error = urllib.error.HTTPError(
            "https://export.arxiv.org/api/query", 400, "Bad Request", {}, io.BytesIO()
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "_open_arxiv", side_effect=error) as open_arxiv,
            mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
            mock.patch.object(fetch_papers.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "400"):
                fetch_papers.fetch_arxiv("world model")

        self.assertEqual(1, open_arxiv.call_count)
        sleep.assert_not_called()

    def test_retry_after_cannot_exceed_remaining_stage_budget(self):
        clock = [0.0]
        error = urllib.error.HTTPError(
            "https://export.arxiv.org/api/query", 429, "Too Many Requests",
            {"Retry-After": "7200"}, io.BytesIO(),
        )

        def advance(seconds):
            clock[0] += seconds

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "_open_arxiv", side_effect=error) as open_arxiv,
            mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
            mock.patch.object(fetch_papers.time, "monotonic", side_effect=lambda: clock[0]),
            mock.patch.object(fetch_papers.time, "sleep", side_effect=advance) as sleep,
        ):
            with self.assertRaisesRegex(TimeoutError, "1 hour"):
                fetch_papers.fetch_arxiv("world model", deadline=60.0)

        self.assertEqual(1, open_arxiv.call_count)
        sleep.assert_called_once_with(60.0)

    def test_retry_after_http_date_is_honored(self):
        retry_at = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120))
        error = urllib.error.HTTPError(
            "https://export.arxiv.org/api/query", 429, "Too Many Requests",
            {"Retry-After": retry_at}, io.BytesIO(),
        )
        self.assertGreater(fetch_papers._retry_after_seconds(error, 30), 118)

    def test_network_timeout_is_limited_by_remaining_budget(self):
        clock = [0.0]
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "ARXIV_CACHE_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "_open_arxiv", side_effect=TimeoutError("network stalled")) as open_arxiv,
            mock.patch.object(fetch_papers, "_wait_for_arxiv_slot"),
            mock.patch.object(fetch_papers.time, "monotonic", side_effect=lambda: clock[0]),
            mock.patch.object(fetch_papers.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)),
        ):
            with self.assertRaisesRegex(TimeoutError, "1 hour"):
                fetch_papers.fetch_arxiv("world model", deadline=12.0)

        self.assertEqual(1, open_arxiv.call_count)
        self.assertEqual(12.0, open_arxiv.call_args.kwargs["timeout"])

    def test_filtered_full_page_does_not_stop_pagination(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "DATA_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "fetch_arxiv", side_effect=[
                atom_page(100, 'first', excluded_last=True), atom_page(1, 'second'),
            ]) as fetch,
            mock.patch.object(fetch_papers.time, "sleep"),
        ):
            result = fetch_papers.fetch_topic('test', {'keywords': ['world model'], 'days': 30})

        self.assertEqual(100, len(result))
        self.assertEqual([0, 100], [call.kwargs['start'] for call in fetch.call_args_list])
        self.assertIn('second-0', {paper['arxiv_id'] for paper in result})

    def test_pagination_stops_when_page_is_older_than_window(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "DATA_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "fetch_arxiv", return_value=atom_page(100, 'old', days_old=31)) as fetch,
            mock.patch.object(fetch_papers.time, "sleep"),
        ):
            result = fetch_papers.fetch_topic('test', {'keywords': ['world model'], 'days': 30})

        self.assertEqual([], result)
        self.assertEqual(1, fetch.call_count)

    def test_later_page_failure_does_not_overwrite_existing_dataset(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "DATA_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "fetch_arxiv", side_effect=[
                atom_page(100, 'first', excluded_last=True), RuntimeError('arXiv unavailable'),
            ]),
            mock.patch.object(fetch_papers.time, "sleep"),
        ):
            path = Path(tmp) / 'test' / 'papers.json'
            path.parent.mkdir()
            original = [{'arxiv_id': 'existing', 'date': '2026-09-01', 'authors': [], 'categories': []}]
            path.write_text(json.dumps(original))
            with self.assertRaisesRegex(RuntimeError, 'arXiv unavailable'):
                fetch_papers.fetch_topic('test', {'keywords': ['world model'], 'days': 30})
            self.assertEqual(original, json.loads(path.read_text()))

    def test_stage_deadline_applies_across_pages_and_keeps_old_dataset(self):
        clock = [0.0]

        def fetch_page(*args, **kwargs):
            if kwargs["start"] == 0:
                clock[0] = 3599.0
                return atom_page(100, "first")
            self.fail("second page should not be attempted past the stage deadline")

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "DATA_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "fetch_arxiv", side_effect=fetch_page) as fetch,
            mock.patch.object(fetch_papers.time, "monotonic", side_effect=lambda: clock[0]),
            mock.patch.object(fetch_papers.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)),
        ):
            path = Path(tmp) / "test" / "papers.json"
            path.parent.mkdir()
            original = [{"arxiv_id": "existing", "date": "2026-09-01", "authors": [], "categories": []}]
            path.write_text(json.dumps(original))
            with self.assertRaisesRegex(TimeoutError, "1 hour"):
                fetch_papers.fetch_topic("test", {"keywords": ["world model"], "days": 30}, deadline=3600.0)
            self.assertEqual(original, json.loads(path.read_text()))

        self.assertEqual(1, fetch.call_count)

    def test_existing_inventory_keeps_full_window_for_late_indexed_papers(self):
        page = ET.fromstring(atom_page(99, 'new'))
        page.append(ET.fromstring(atom_page(1, 'old', days_old=9))[0])
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(fetch_papers, "DATA_DIR", Path(tmp)),
            mock.patch.object(fetch_papers, "fetch_arxiv", side_effect=[
                ET.tostring(page, encoding='unicode'), atom_page(0, 'end'),
            ]) as fetch,
            mock.patch.object(fetch_papers.time, "sleep"),
        ):
            path = Path(tmp) / 'test' / 'papers.json'
            path.parent.mkdir()
            original = [{'arxiv_id': 'existing', 'date': (datetime.now() - timedelta(days=7)).date().isoformat(), 'authors': [], 'categories': []}]
            path.write_text(json.dumps(original))
            result = fetch_papers.fetch_topic('test', {'keywords': ['world model'], 'days': 30})

        self.assertEqual(2, fetch.call_count)
        self.assertEqual(101, len(result))
        self.assertIn('existing', {p['arxiv_id'] for p in result})
        self.assertIn('old-0', {p['arxiv_id'] for p in result})


if __name__ == "__main__":
    unittest.main()
