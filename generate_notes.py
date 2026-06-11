#!/usr/bin/env python3
"""Find papers needing notes or metadata and prepare batch data for Codex."""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = BASE_DIR / "notes"
TOPIC = "world_model"


def note_stem(arxiv_id: str) -> str:
    return arxiv_id.replace("/", "_").replace(".", "_")


def is_complete(paper: dict, has_note: bool) -> bool:
    if not has_note:
        return False
    if not (paper.get("tldr") or "").strip():
        return False
    rating = paper.get("rating") or 0
    if rating <= 0:
        return False
    return True


def main():
    json_path = DATA_DIR / TOPIC / "papers.json"
    if not json_path.exists():
        print("No papers.json found")
        return

    with open(json_path, encoding="utf-8") as f:
        papers = json.load(f)

    notes_dir = NOTES_DIR / TOPIC
    notes_dir.mkdir(parents=True, exist_ok=True)
    existing_notes = {md.stem.replace("_", ".") for md in notes_dir.glob("*.md")}

    todo = []
    missing_note = missing_tldr = missing_rating = 0
    for p in papers:
        aid = p["arxiv_id"]
        has_note = aid in existing_notes
        if is_complete(p, has_note):
            continue
        if not has_note:
            missing_note += 1
        if not (p.get("tldr") or "").strip():
            missing_tldr += 1
        if not (p.get("rating") or 0):
            missing_rating += 1
        todo.append(p)

    if not todo:
        print("All papers have notes and ratings, nothing to do.")
        return

    pdf_dir = DATA_DIR / TOPIC / "pdfs"
    for p in todo:
        aid = p["arxiv_id"]
        p["pdf_path"] = str(pdf_dir / (note_stem(aid) + ".pdf"))
        reasons = []
        if aid not in existing_notes:
            reasons.append("no note")
        if not (p.get("tldr") or "").strip():
            reasons.append("no tldr")
        if not (p.get("rating") or 0):
            reasons.append("no rating")
        p["gap_reasons"] = reasons

    batch_path = DATA_DIR / TOPIC / "batch_new.json"
    with open(batch_path, "w", encoding="utf-8") as f:
        json.dump(todo, f, ensure_ascii=False, indent=2)

    print(
        f"{len(todo)} papers need processing "
        f"(missing note: {missing_note}, tldr: {missing_tldr}, rating: {missing_rating}) "
        f"-> {batch_path}"
    )
    sys.exit(42)


if __name__ == "__main__":
    main()
