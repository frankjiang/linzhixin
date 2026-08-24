#!/usr/bin/env python3
"""Sync tldr/rating/relevance from note markdown into papers.json."""

import re
from pathlib import Path

from paper_store import load_papers, save_papers

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = BASE_DIR / "notes"
TOPIC = "world_model"


def parse_note(text: str) -> dict:
    result = {}

    tldr_match = re.search(r"^## TL;DR\s*\n(.+?)(?=\n## |\Z)", text, re.MULTILINE | re.DOTALL)
    if tldr_match:
        result["tldr"] = tldr_match.group(1).strip()

    rating_match = re.search(r"Innovation:\s*(\d)/5", text, re.IGNORECASE)
    if rating_match:
        result["rating"] = int(rating_match.group(1))

    rel_match = re.search(r"Relevance:\s*(\d)/3", text, re.IGNORECASE)
    if rel_match:
        result["relevance"] = int(rel_match.group(1))

    return result


def main():
    json_path = DATA_DIR / TOPIC / "papers.json"
    if not json_path.exists():
        print("No papers.json found")
        return

    papers = load_papers(json_path)

    notes_dir = NOTES_DIR / TOPIC
    if not notes_dir.exists():
        print("No notes directory found")
        return

    notes_by_id = {}
    for md_file in notes_dir.glob("*.md"):
        arxiv_id = md_file.stem.replace("_", ".")
        notes_by_id[arxiv_id] = parse_note(md_file.read_text(encoding="utf-8"))

    updated = 0
    for p in papers:
        parsed = notes_by_id.get(p["arxiv_id"])
        if not parsed:
            continue
        incomplete = not (p.get("tldr") or "").strip() or not (p.get("rating") or 0)
        changed = False
        if parsed.get("tldr") and not (p.get("tldr") or "").strip():
            p["tldr"] = parsed["tldr"]
            changed = True
        if parsed.get("rating") and not (p.get("rating") or 0):
            p["rating"] = parsed["rating"]
            changed = True
        if "relevance" in parsed and incomplete:
            p["relevance"] = parsed["relevance"]
            changed = True
        if changed:
            updated += 1

    if updated:
        save_papers(json_path, papers)
    print(f"Synced metadata from notes for {updated} papers")


if __name__ == "__main__":
    main()
