import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


from paper_store import load_papers, save_papers


class PaperStoreTests(unittest.TestCase):
    def test_failed_write_keeps_primary_file_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papers.json"
            original = [{"arxiv_id": "old", "date": "2026-08-01"}]
            path.write_text(json.dumps(original), encoding="utf-8")

            with mock.patch("paper_store.json.dump", side_effect=OSError(errno.ENOSPC, "disk full")):
                with self.assertRaises(OSError):
                    save_papers(path, [{"arxiv_id": "new", "date": "2026-08-02"}])

            self.assertEqual(original, json.loads(path.read_text(encoding="utf-8")))

    def test_save_preserves_last_valid_primary_as_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papers.json"
            original = [{"arxiv_id": "old", "date": "2026-08-01"}]
            updated = [{"arxiv_id": "new", "date": "2026-08-02"}]
            path.write_text(json.dumps(original), encoding="utf-8")

            save_papers(path, updated)

            self.assertEqual(updated, json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(original, json.loads((Path(str(path) + ".bak")).read_text(encoding="utf-8")))

    def test_invalid_primary_falls_back_to_valid_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papers.json"
            backup = Path(str(path) + ".bak")
            expected = [{"arxiv_id": "safe", "date": "2026-08-01"}]
            path.write_text("", encoding="utf-8")
            backup.write_text(json.dumps(expected), encoding="utf-8")

            self.assertEqual(expected, load_papers(path))

    def test_invalid_primary_without_backup_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "papers.json"
            path.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "invalid and no valid backup"):
                load_papers(path)


if __name__ == "__main__":
    unittest.main()
