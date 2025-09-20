"""Utility for sending Telegram messages with a WebApp button."""

from __future__ import annotations

import argparse
import logging
from typing import Any, Dict

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def send_tg_with_webapp(summary_text: str, cid: str) -> Dict[str, Any]:
    """Send a Telegram message with an inline WebApp button."""
    settings = get_settings()
    if not settings.tg_chat_id:
        raise RuntimeError("TG_CHAT_ID is not configured")

    webapp_url = f"{settings.app_base_url}/webapp/?cid={cid}"
    payload = {
        "chat_id": settings.tg_chat_id,
        "text": summary_text,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {
                        "text": "✏️ Редактировать",
                        "web_app": {"url": webapp_url},
                    }
                ]
            ]
        },
        "disable_web_page_preview": True,
    }

    api_url = f"https://api.telegram.org/bot{settings.tg_token}/sendMessage"
    with httpx.Client(timeout=10.0) as client:
        response = client.post(api_url, json=payload)
        response.raise_for_status()
        logger.info("Telegram message sent", extra={"cid": cid})
        return response.json()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send Telegram message with WebApp button")
    parser.add_argument("cid", help="Client identifier used in Nightscout treatment")
    parser.add_argument("summary", help="Message text to send")
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    send_tg_with_webapp(args.summary, args.cid)
