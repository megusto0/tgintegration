from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

import httpx

from app.config import get_settings

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


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
            if exc.response.status_code != 404 or existing is None:
                raise

            fallback_url = f"{settings.ns_url}/api/v1/treatments.json"
            fallback_document = existing.copy()
            fallback_document.update(patch)
            fallback_document["_id"] = treatment_id
            fallback_payload = [fallback_document]

            fallback_response = await client.put(
                fallback_url,
                json=fallback_payload,
                headers=auth["headers"],
                params=auth["params"],
            )
            fallback_response.raise_for_status()

            if not fallback_response.content:
                return {"status": "ok"}

            content_type = fallback_response.headers.get("content-type", "")
            if "application/json" in content_type:
                return fallback_response.json()
            return {"status": fallback_response.text.strip() or "ok"}

        return response.json()
