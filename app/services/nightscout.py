from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import get_settings

TIMEOUT = httpx.Timeout(10.0, connect=5.0)

logger = logging.getLogger(__name__)


def _auth_headers_params() -> Dict[str, Dict[str, str]]:
    settings = get_settings()
    headers: Dict[str, str] = {}
    params: Dict[str, str] = {}

    if settings.ns_token:
        params["token"] = settings.ns_token
    if settings.ns_api_secret:
        digest = hashlib.sha1(settings.ns_api_secret.encode("utf-8")).hexdigest()
        headers["api-secret"] = digest
    return {"headers": headers, "params": params}


async def fetch_treatment_by_client_id(client_id: str) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    auth = _auth_headers_params()
    url = f"{settings.ns_url}/api/v1/treatments.json"
    query = {"find[clientId]": client_id, "count": 1, **auth["params"]}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url, params=query, headers=auth["headers"])
        response.raise_for_status()
        payload = response.json()
        if not payload:
            return None
        return payload[0]


async def fetch_treatment_by_id(treatment_id: str) -> Optional[Dict[str, Any]]:
    settings = get_settings()
    auth = _auth_headers_params()
    url = f"{settings.ns_url}/api/v1/treatments.json"
    query = {"find[_id]": treatment_id, "count": 1, **auth["params"]}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url, params=query, headers=auth["headers"])
        response.raise_for_status()
        payload = response.json()
        if not payload:
            return None
        return payload[0]


async def update_treatment(
    treatment_id: str,
    patch: Dict[str, Any],
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    auth = _auth_headers_params()
    url = f"{settings.ns_url}/api/v1/treatments/{treatment_id}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(url, json=patch, params=auth["params"], headers=auth["headers"])
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_preview = (exc.response.text or "").strip()
            logger.warning(
                "Nightscout PUT %s failed with %s: %s",
                treatment_id,
                exc.response.status_code,
                body_preview[:300],
            )
            if exc.response.status_code != 404 or existing is None:
                raise

            delete_url = f"{settings.ns_url}/api/v1/treatments/{treatment_id}"
            delete_response = await client.delete(
                delete_url,
                headers=auth["headers"],
                params=auth["params"],
            )
            if delete_response.status_code not in {200, 404}:
                delete_response.raise_for_status()

            fallback_document = existing.copy()
            fallback_document.update(patch)

            insert_document = fallback_document.copy()
            insert_document.pop("_id", None)
            fallback_url = f"{settings.ns_url}/api/v1/treatments"
            fallback_payload = [insert_document]

            fallback_response = await client.post(
                fallback_url,
                json=fallback_payload,
                headers=auth["headers"],
                params=auth["params"],
            )
            try:
                fallback_response.raise_for_status()
            except httpx.HTTPStatusError as fallback_exc:
                fallback_body = (fallback_exc.response.text or "").strip()
                logger.error(
                    "Nightscout fallback recreate failed for %s with %s: %s",
                    treatment_id,
                    fallback_exc.response.status_code,
                    fallback_body[:300],
                )

                original_document = existing.copy()
                original_document.pop("_id", None)
                try:
                    restore_response = await client.post(
                        fallback_url,
                        json=[original_document],
                        headers=auth["headers"],
                        params=auth["params"],
                    )
                    restore_response.raise_for_status()
                except Exception:  # pragma: no cover - best-effort restore
                    logger.exception("Nightscout restore attempt failed for %s", treatment_id)

                raise

            if not fallback_response.content:
                return {"status": "ok"}

            content_type = fallback_response.headers.get("content-type", "")
            if "application/json" in content_type:
                return fallback_response.json()
            return {"status": fallback_response.text.strip() or "ok"}

        return response.json()
