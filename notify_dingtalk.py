#!/usr/bin/env python3
"""Send DingTalk notifications for newly processed high-rated papers."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, load_config, topic_name
from dingtalk_util import resolve_bot_url, send_markdown

DATA_DIR = BASE_DIR / "data"
MAX_MESSAGE_CHARS = 18000

RELEVANCE_LABELS = {
    3: "Core",
    2: "Related",
    1: "Tangential",
    0: "Noise",
}


def _load_run_batch(topic: str) -> list[dict]:
    batch_path = DATA_DIR / topic / "run_batch.json"
    if not batch_path.exists():
        return []
    with open(batch_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _load_papers(topic: str) -> dict[str, dict]:
    json_path = DATA_DIR / topic / "papers.json"
    if not json_path.exists():
        return {}
    with open(json_path, encoding="utf-8") as f:
        papers = json.load(f)
    return {p["arxiv_id"]: p for p in papers}


def _survey_paper_url(survey_url: str, arxiv_id: str) -> str:
    base = survey_url.rstrip("/")
    quoted = urllib.parse.quote(arxiv_id, safe="")
    return f"{base}?paper={quoted}"


def _format_paper_block(paper: dict, index: int, survey_url: str) -> str:
    stars = "⭐" * int(paper.get("rating") or 0)
    rel = RELEVANCE_LABELS.get(paper.get("relevance", 0), str(paper.get("relevance", "")))
    tldr = (paper.get("tldr") or "").strip() or "（暂无摘要）"
    title = paper.get("title", paper.get("arxiv_id", ""))
    url = paper.get("url", "")
    aid = paper.get("arxiv_id", "")
    date = paper.get("date", "")
    read_url = _survey_paper_url(survey_url, aid)
    return (
        f"#### {index}. {title}\n\n"
        f"{stars} · 相关度 **{rel}** · {date}  \n"
        f"[{aid}]({url}) · [快速阅读]({read_url})\n\n"
        f"**摘要**  {tldr}"
    )


def build_message(
    highlights: list[dict],
    survey_url: str,
    min_rating: int,
    *,
    catch_up: bool = False,
    start_index: int = 1,
) -> tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    count = len(highlights)
    suffix = "（补发）" if catch_up else ""
    title = f"Paper Survey · {count} 篇 {min_rating}⭐+ 论文{suffix}"

    if catch_up:
        header = (
            f"## 📚 World Model 日报\n\n"
            f"**{today}** · 补发 **{count}** 篇高价值论文（创新度 ≥ {min_rating}⭐）"
        )
    else:
        header = (
            f"## 📚 World Model 日报\n\n"
            f"**{today}** · 本次发现 **{count}** 篇高价值论文（创新度 ≥ {min_rating}⭐）"
        )
    blocks = [
        _format_paper_block(p, i, survey_url)
        for i, p in enumerate(highlights, start_index)
    ]
    body = "\n\n---\n\n".join(blocks)
    footer = f"\n\n---\n\n[📖 查看完整列表]({survey_url})"

    return title, header + "\n\n---\n\n" + body + footer


def _dingtalk_settings(cfg: dict) -> tuple[dict, str, int, str] | None:
    dingtalk = cfg.get("dingtalk", {})
    site = cfg.get("site", {})
    server = cfg.get("server", {})
    address = server.get("address", "127.0.0.1")
    port = server.get("port", 7777)
    default_url = f"http://{address}:{port}"

    if not dingtalk.get("enabled"):
        print("DingTalk notifications disabled in config.")
        return None

    webhook = str(dingtalk.get("webhook", "")).strip()
    if not webhook:
        print("DingTalk webhook not configured, skipping.")
        return None

    min_rating = int(dingtalk.get("min_rating", 4))
    survey_url = (
        str(dingtalk.get("survey_url", "")).strip()
        or str(site.get("public_url", "")).strip()
        or default_url
    )
    return dingtalk, webhook, min_rating, survey_url


def _filter_highlights(
    papers: list[dict],
    min_rating: int,
    since_date: str | None = None,
) -> list[dict]:
    highlights = []
    for paper in papers:
        if since_date and (paper.get("date") or "") < since_date:
            continue
        rating = int(paper.get("rating") or 0)
        if rating >= min_rating and (paper.get("tldr") or "").strip():
            highlights.append(paper)
    highlights.sort(
        key=lambda p: (int(p.get("rating") or 0), p.get("date", "")),
        reverse=True,
    )
    return highlights


def _send_highlights(
    highlights: list[dict],
    *,
    catch_up: bool = False,
) -> int:
    if not highlights:
        return 0

    cfg = load_config()
    settings = _dingtalk_settings(cfg)
    if not settings:
        return 0

    _, _, min_rating, survey_url = settings
    url = resolve_bot_url(load_config(), "dingtalk")
    if not url:
        return 0

    chunks: list[list[dict]] = []
    current: list[dict] = []
    for paper in highlights:
        trial = current + [paper]
        _, text = build_message(trial, survey_url, min_rating, catch_up=catch_up)
        if current and len(text) > MAX_MESSAGE_CHARS:
            chunks.append(current)
            current = [paper]
        else:
            current = trial
    if current:
        chunks.append(current)

    sent = 0
    index = 1
    for chunk in chunks:
        part_suffix = f" ({index}/{len(chunks)})" if len(chunks) > 1 else ""
        title, text = build_message(
            chunk,
            survey_url,
            min_rating,
            catch_up=catch_up,
            start_index=index,
        )
        title += part_suffix
        send_markdown(url, title, text)
        sent += len(chunk)
        index += len(chunk)
        if len(chunks) > 1:
            time.sleep(1)

    print(f"DingTalk notification sent for {sent} paper(s).")
    return sent


def notify_highlights() -> int:
    cfg = load_config()
    settings = _dingtalk_settings(cfg)
    if not settings:
        return 0

    _, _, min_rating, _ = settings
    topic = topic_name(cfg)

    batch = _load_run_batch(topic)
    if not batch:
        print("No run_batch.json found, nothing to notify.")
        return 0

    papers_map = _load_papers(topic)
    batch_papers = [
        papers_map.get(item["arxiv_id"], item)
        for item in batch
        if item.get("arxiv_id")
    ]
    highlights = _filter_highlights(batch_papers, min_rating)

    if not highlights:
        print(f"No papers rated >={min_rating} in this batch.")
        _clear_run_batch(topic)
        return 0

    sent = _send_highlights(highlights)
    _clear_run_batch(topic)
    return sent


def resend_since(since_date: str, *, clear_batch: bool = True) -> int:
    cfg = load_config()
    settings = _dingtalk_settings(cfg)
    if not settings:
        return 0

    _, _, min_rating, _ = settings
    topic = topic_name(cfg)
    papers_map = _load_papers(topic)
    highlights = _filter_highlights(list(papers_map.values()), min_rating, since_date)

    if not highlights:
        print(f"No papers rated >={min_rating} since {since_date}.")
        return 0

    print(f"Resending {len(highlights)} paper(s) since {since_date}...")
    sent = _send_highlights(highlights, catch_up=True)
    if clear_batch:
        _clear_run_batch(topic)
    return sent


def _clear_run_batch(topic: str) -> None:
    batch_path = DATA_DIR / topic / "run_batch.json"
    if batch_path.exists():
        batch_path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Send DingTalk paper highlights")
    parser.add_argument(
        "--resend-since",
        metavar="YYYY-MM-DD",
        help="Resend all qualifying papers on/after this date (catch-up mode)",
    )
    parser.add_argument(
        "--keep-batch",
        action="store_true",
        help="With --resend-since, do not clear run_batch.json afterward",
    )
    args = parser.parse_args()

    try:
        if args.resend_since:
            count = resend_since(args.resend_since, clear_batch=not args.keep_batch)
        else:
            count = notify_highlights()
        if count:
            print(f"Notified {count} high-rated paper(s).")
    except Exception as exc:
        print(f"DingTalk notification failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
