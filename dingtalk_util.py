#!/usr/bin/env python3
"""Shared DingTalk robot helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request
from typing import Any

DINGTALK_DEFAULT_BASE = "https://oapi.dingtalk.com/robot/send"


def build_dingtalk_url(webhook: str, secret: str) -> str:
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


def send_markdown(url: str, title: str, text: str) -> dict:
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


def resolve_bot_url(cfg: dict[str, Any], section: str) -> str | None:
    """Return signed webhook URL for a config section, or None if disabled."""
    bot = cfg.get(section, {})
    if not bot.get("enabled"):
        return None
    webhook = str(bot.get("webhook", "")).strip()
    if not webhook:
        return None
    secret = str(bot.get("secret", "")).strip()
    url = build_dingtalk_url(webhook, secret)
    return url or None
