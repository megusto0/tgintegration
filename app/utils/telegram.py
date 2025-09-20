from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import HTTPException, status

from app.config import get_settings


def _compute_hash(data_check_string: str) -> str:
    settings = get_settings()
    secret_key = hashlib.sha256(settings.tg_token.encode("utf-8")).digest()
    signature = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256)
    return signature.hexdigest()


def _prepare_data_check_string(init_data: str) -> Dict[str, Any]:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    if "hash" not in parsed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing signature")
    received_hash = parsed.pop("hash")
    data_check_pairs = [f"{k}={v}" for k, v in sorted(parsed.items())]
    data_check_string = "\n".join(data_check_pairs)
    expected_hash = _compute_hash(data_check_string)

    if not hmac.compare_digest(received_hash, expected_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    return {"data": parsed, "hash": received_hash}


def verify_init_data(init_data: str) -> Dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing init data")

    prepared = _prepare_data_check_string(init_data)
    data = prepared["data"]

    user_payload = data.get("user")
    if not user_payload:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing user info")

    try:
        user_data = json.loads(user_payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user info") from exc

    allowed_ids = set(get_settings().allowed_user_ids)
    user_id = user_data.get("id")
    if not allowed_ids or user_id not in allowed_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not allowed")

    return {"raw": data, "user": user_data}
