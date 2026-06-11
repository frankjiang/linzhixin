#!/usr/bin/env python3
"""Retire old papers by rating-based retention policy."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from config import load_config, topic_name

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
NOTES_DIR = BASE_DIR / "notes"

DEFAULT_RETENTION_DAYS = {
    1: 30,
    2: 60,
    3: 180,
    4: 365,
    5: 365,
}


def note_stem(arxiv_id: str) -> str:
    return arxiv_id.replace("/", "_").replace(".", "_")


def retention_days(cfg: dict) -> dict[int, int]:
    retirement = cfg.get("retirement", {})
    raw = retirement.get("days_by_rating", DEFAULT_RETENTION_DAYS)
    if isinstance(raw, dict):
        return {int(k): int(v) for k, v in raw.items()}
    return dict(DEFAULT_RETENTION_DAYS)


def paper_age_days(paper: dict, today: datetime | None = None) -> int:
    today = today or datetime.now()
    paper_date = datetime.strptime(paper["date"], "%Y-%m-%d")
    return (today - paper_date).days


def should_retire(paper: dict, policy: dict[int, int], today: datetime | None = None) -> bool:
    rating = int(paper.get("rating") or 0)
    if rating <= 0:
        return False
    max_days = policy.get(rating)
    if max_days is None:
        return False
    return paper_age_days(paper, today) > max_days


def save_csv(papers: list[dict], csv_path: Path) -> None:
    fields = [
        "arxiv_id", "title", "date", "authors", "categories",
        "affiliations", "tldr", "rating", "relevance", "url", "pdf_url",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for p in papers:
            row = dict(p)
            row["authors"] = "; ".join(p["authors"])
            row["categories"] = "; ".join(p["categories"])
            row["affiliations"] = "; ".join(p.get("affiliations", []))
            writer.writerow(row)


def retire_paper_files(topic: str, arxiv_id: str) -> list[str]:
    removed: list[str] = []
    note_path = NOTES_DIR / topic / f"{note_stem(arxiv_id)}.md"
    pdf_path = DATA_DIR / topic / "pdfs" / f"{note_stem(arxiv_id)}.pdf"
    for path in (note_path, pdf_path):
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return removed


def main():
    cfg = load_config()
    retirement_cfg = cfg.get("retirement", {})
    if not retirement_cfg.get("enabled", True):
        print("Paper retirement disabled in config.")
        return

    topic = topic_name(cfg)
    policy = retention_days(cfg)
    json_path = DATA_DIR / topic / "papers.json"
    csv_path = DATA_DIR / topic / "papers.csv"

    if not json_path.exists():
        print("No papers.json found, skipping retirement.")
        return

    with open(json_path, encoding="utf-8") as f:
        papers = json.load(f)

    today = datetime.now()
    kept: list[dict] = []
    retired: list[dict] = []

    for paper in papers:
        if should_retire(paper, policy, today):
            retired.append(paper)
        else:
            kept.append(paper)

    if not retired:
        print("No papers to retire.")
        return

    for paper in retired:
        aid = paper["arxiv_id"]
        rating = int(paper.get("rating") or 0)
        age = paper_age_days(paper, today)
        files = retire_paper_files(topic, aid)
        file_msg = f", removed {len(files)} file(s)" if files else ""
        print(
            f"  Retired: {aid} (rating={rating}, age={age}d, "
            f"limit={policy.get(rating)}d){file_msg}"
        )

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)
    save_csv(kept, csv_path)

    print(f"Retired {len(retired)} paper(s), {len(kept)} remaining.")


if __name__ == "__main__":
    main()
