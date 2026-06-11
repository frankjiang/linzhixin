#!/usr/bin/env python3
"""Send DingTalk notifications for newly processed high-rated papers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, load_config, topic_name

DATA_DIR = BASE_DIR / "data"
DINGTALK_DEFAULT_BASE = "https://oapi.dingtalk.com/robot/send"

RELEVANCE_LABELS = {
    3: "Core",
    2: "Related",
    1: "Tangential",
    0: "Noise",
}


def _build_dingtalk_url(webhook: str, secret: str) -> str:
    raw = webhook.strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        base = raw
    else:
        base = f"{DINGTALK_DEFAULT_BASE}?access_token={urllib.parse.quote_plus(raw)}"

    if not secret:
        return base

    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

    parsed = urllib.parse.urlparse(base)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k not in {"timestamp", "sign"}]
    query.append(("timestamp", timestamp))
    query.append(("sign", sign))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def _send_markdown(url: str, title: str, text: str) -> dict:
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
    result = json.loads(body)
    if result.get("errcode") != 0:
        raise RuntimeError(f"DingTalk API error: {result}")
    return result


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


def build_message(highlights: list[dict], survey_url: str, min_rating: int) -> tuple[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    count = len(highlights)
    title = f"Paper Survey · {count} 篇 {min_rating}⭐+ 论文"

    header = (
        f"## 📚 World Model 日报\n\n"
        f"**{today}** · 本次发现 **{count}** 篇高价值论文（创新度 ≥ {min_rating}⭐）"
    )
    blocks = [_format_paper_block(p, i, survey_url) for i, p in enumerate(highlights, 1)]
    body = "\n\n---\n\n".join(blocks)
    footer = f"\n\n---\n\n[📖 查看完整列表]({survey_url})"

    return title, header + "\n\n---\n\n" + body + footer


def notify_highlights() -> int:
    cfg = load_config()
    dingtalk = cfg.get("dingtalk", {})
    site = cfg.get("site", {})
    server = cfg.get("server", {})
    address = server.get("address", "127.0.0.1")
    port = server.get("port", 7777)
    default_url = f"http://{address}:{port}"
    if not dingtalk.get("enabled"):
        print("DingTalk notifications disabled in config.")
        return 0

    webhook = str(dingtalk.get("webhook", "")).strip()
    if not webhook:
        print("DingTalk webhook not configured, skipping.")
        return 0

    topic = topic_name(cfg)
    min_rating = int(dingtalk.get("min_rating", 4))
    survey_url = (
        str(dingtalk.get("survey_url", "")).strip()
        or str(site.get("public_url", "")).strip()
        or default_url
    )

    batch = _load_run_batch(topic)
    if not batch:
        print("No run_batch.json found, nothing to notify.")
        return 0

    papers_map = _load_papers(topic)
    highlights = []
    for item in batch:
        aid = item.get("arxiv_id")
        if not aid:
            continue
        paper = papers_map.get(aid, item)
        rating = int(paper.get("rating") or 0)
        if rating >= min_rating and (paper.get("tldr") or "").strip():
            highlights.append(paper)

    if not highlights:
        print(f"No papers rated >={min_rating} in this batch.")
        _clear_run_batch(topic)
        return 0

    highlights.sort(key=lambda p: (int(p.get("rating") or 0), p.get("date", "")), reverse=True)

    url = _build_dingtalk_url(webhook, str(dingtalk.get("secret", "")).strip())
    title, text = build_message(highlights, survey_url, min_rating)
    _send_markdown(url, title, text)
    print(f"DingTalk notification sent for {len(highlights)} paper(s).")
    _clear_run_batch(topic)
    return len(highlights)


def _clear_run_batch(topic: str) -> None:
    batch_path = DATA_DIR / topic / "run_batch.json"
    if batch_path.exists():
        batch_path.unlink()


def main():
    try:
        count = notify_highlights()
        if count:
            print(f"Notified {count} high-rated paper(s).")
    except Exception as exc:
        print(f"DingTalk notification failed: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
