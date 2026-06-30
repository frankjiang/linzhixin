#!/usr/bin/env python3
"""Send operational alerts to the manager DingTalk robot."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, load_config
from dingtalk_util import resolve_bot_url, send_markdown

MAX_ALERT_CHARS = 8000
MAX_ITEMS = 30


def _dedupe_errors(errors: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in errors:
        line = item.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return unique


def build_alert_message(errors: list[str], *, log_path: str | None = None) -> tuple[str, str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = len(errors)
    title = f"Paper Survey 告警 · {count} 项"

    header = f"## ⚠️ 林知新日报运行告警\n\n**{now}** · 共 **{count}** 个问题"
    if log_path:
        header += f"\n\n日志：`{log_path}`"

    items = errors[:MAX_ITEMS]
    body = "\n\n".join(f"{i}. {err}" for i, err in enumerate(items, 1))
    if count > MAX_ITEMS:
        body += f"\n\n… 另有 {count - MAX_ITEMS} 项未展示"

    text = f"{header}\n\n---\n\n{body}"
    if len(text) > MAX_ALERT_CHARS:
        text = text[: MAX_ALERT_CHARS - 20] + "\n\n…（消息已截断）"
    return title, text


def send_manager_alerts(
    errors: list[str],
    *,
    log_path: str | None = None,
) -> bool:
    errors = _dedupe_errors(errors)
    if not errors:
        print("No errors to report.")
        return False

    cfg = load_config()
    url = resolve_bot_url(cfg, "dingtalk_manager")
    if not url:
        print("Manager DingTalk disabled or not configured, skipping alert.")
        return False

    title, text = build_alert_message(errors, log_path=log_path)
    send_markdown(url, title, text)
    print(f"Manager alert sent ({len(errors)} item(s)).")
    return True


def _load_errors_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Send manager DingTalk alerts")
    parser.add_argument(
        "messages",
        nargs="*",
        help="Error messages to include in the alert",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="Read one error per line from a file",
    )
    parser.add_argument(
        "--log",
        metavar="PATH",
        help="Log file path to show in the alert (default: today's daily log)",
    )
    args = parser.parse_args()

    errors: list[str] = list(args.messages)
    if args.file:
        errors.extend(_load_errors_file(Path(args.file)))

    log_path = args.log
    if log_path is None and args.file:
        today = datetime.now().strftime("%Y%m%d")
        default_log = BASE_DIR / "logs" / f"{today}.log"
        if default_log.exists():
            log_path = str(default_log)

    try:
        send_manager_alerts(errors, log_path=log_path)
        return 0
    except Exception as exc:
        print(f"Manager alert failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
