"""Notification channel implementations.

Each channel is a simple async callable:
    send(subject, body, attachments: list[Attachment]) → bool

Channels use httpx for HTTP and smtplib for email. All are fire-and-forget
at the dispatcher level — a channel failure never blocks other channels or
the watcher loop.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Timeout for external HTTP calls.
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass
class Attachment:
    filename: str
    data: bytes
    content_type: str  # e.g. "image/jpeg", "video/mp4"


# ── Telegram ─────────────────────────────────────────────────────

async def send_telegram(
    cfg: dict, subject: str, body: str, attachments: list[Attachment],
) -> bool:
    token = cfg["bot_token"]
    chat_id = cfg["chat_id"]
    base = f"https://api.telegram.org/bot{token}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Text message.
        text = f"*{_escape_md(subject)}*\n{_escape_md(body)}"
        r = await client.post(
            f"{base}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"},
        )
        if r.status_code != 200:
            log.warning("telegram sendMessage failed: %s", r.text)
            return False

        # Attachments.
        for att in attachments:
            if att.content_type.startswith("image/"):
                endpoint = "sendPhoto"
                field = "photo"
            elif att.content_type.startswith("video/"):
                endpoint = "sendDocument"
                field = "document"
            else:
                endpoint = "sendDocument"
                field = "document"
            r = await client.post(
                f"{base}/{endpoint}",
                data={"chat_id": chat_id},
                files={field: (att.filename, att.data, att.content_type)},
            )
            if r.status_code != 200:
                log.warning("telegram %s failed: %s", endpoint, r.text)

    return True


def _escape_md(s: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    for c in r"_*[]()~`>#+-=|{}.!":
        s = s.replace(c, f"\\{c}")
    return s


# ── Discord ──────────────────────────────────────────────────────

async def send_discord(
    cfg: dict, subject: str, body: str, attachments: list[Attachment],
) -> bool:
    url = cfg["webhook_url"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        files_dict: dict[str, Any] = {}
        for i, att in enumerate(attachments):
            files_dict[f"file{i}"] = (att.filename, att.data, att.content_type)
        payload = {"content": f"**{subject}**\n{body}"}
        if files_dict:
            r = await client.post(
                url, data={"payload_json": __import__("json").dumps(payload)},
                files=files_dict,
            )
        else:
            r = await client.post(url, json=payload)
        ok = 200 <= r.status_code < 300
        if not ok:
            log.warning("discord webhook failed %s: %s", r.status_code, r.text)
        return ok


# ── Email (SMTP) ─────────────────────────────────────────────────

async def send_email(
    cfg: dict, subject: str, body: str, attachments: list[Attachment],
) -> bool:
    """Blocking SMTP send wrapped in a thread to avoid starving the event loop."""
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _smtp_send, cfg, subject, body, attachments)


def _smtp_send(
    cfg: dict, subject: str, body: str, attachments: list[Attachment],
) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = cfg["to_addr"]
    msg.set_content(body)

    for att in attachments:
        maintype, subtype = att.content_type.split("/", 1)
        msg.add_attachment(
            att.data,
            maintype=maintype,
            subtype=subtype,
            filename=att.filename,
        )
    try:
        host = cfg.get("smtp_host", "localhost")
        port = int(cfg.get("smtp_port", 587))
        user = cfg.get("smtp_user", "")
        passwd = cfg.get("smtp_pass", "")
        use_tls = cfg.get("smtp_tls", True)

        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            if use_tls:
                s.starttls()
                s.ehlo()
            if user:
                s.login(user, passwd)
            s.send_message(msg)
        return True
    except Exception:
        log.exception("SMTP send failed")
        return False


# ── ntfy.sh ──────────────────────────────────────────────────────

async def send_ntfy(
    cfg: dict, subject: str, body: str, attachments: list[Attachment],
) -> bool:
    server = cfg.get("server", "https://ntfy.sh").rstrip("/")
    topic = cfg["topic"]
    url = f"{server}/{topic}"

    headers: dict[str, str] = {
        "Title": subject,
        "Priority": cfg.get("priority", "default"),
    }
    auth = cfg.get("auth", "")
    if auth:
        headers["Authorization"] = f"Bearer {auth}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        if attachments:
            att = attachments[0]
            headers["Filename"] = att.filename
            r = await client.post(url, content=att.data, headers=headers)
        else:
            r = await client.post(url, content=body, headers=headers)
        ok = 200 <= r.status_code < 300
        if not ok:
            log.warning("ntfy send failed %s: %s", r.status_code, r.text)
        return ok


# ── Generic webhook ──────────────────────────────────────────────

async def send_webhook(
    cfg: dict, subject: str, body: str, attachments: list[Attachment],
) -> bool:
    url = cfg["url"]
    method = cfg.get("method", "POST").upper()
    payload = {
        "subject": subject,
        "body": body,
        "attachments": [
            {"filename": a.filename, "content_type": a.content_type, "size": len(a.data)}
            for a in attachments
        ],
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.request(method, url, json=payload)
        ok = 200 <= r.status_code < 300
        if not ok:
            log.warning("webhook send failed %s: %s", r.status_code, r.text)
        return ok


# ── dispatcher ───────────────────────────────────────────────────

CHANNEL_SENDERS = {
    "telegram": send_telegram,
    "discord": send_discord,
    "email": send_email,
    "ntfy": send_ntfy,
    "webhook": send_webhook,
}


async def dispatch(
    channels: list[dict],
    subject: str,
    body: str,
    attachments: list[Attachment] | None = None,
) -> dict[str, bool]:
    """Send to every enabled channel. Returns {channel_id: success}."""
    results: dict[str, bool] = {}
    for ch in channels:
        if not ch.get("enabled"):
            continue
        ctype = ch.get("type", "")
        sender = CHANNEL_SENDERS.get(ctype)
        if not sender:
            log.warning("unknown channel type %r", ctype)
            results[ch["id"]] = False
            continue
        try:
            # Filter attachments by channel preference.
            atts = attachments or []
            if not ch.get("send_snapshot", True):
                atts = [a for a in atts if a.content_type != "image/jpeg"]
            if not ch.get("send_timelapse", True):
                atts = [a for a in atts if a.content_type != "video/mp4"]
            ok = await sender(ch["config"], subject, body, atts)
            results[ch["id"]] = ok
        except Exception:
            log.exception("channel %s (%s) send error", ch["id"], ctype)
            results[ch["id"]] = False
    return results
