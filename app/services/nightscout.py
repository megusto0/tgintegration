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
    url = f"{settings.ns_url}/api/v1/treatments/{treatment_id}.json"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url, params=auth["params"], headers=auth["headers"])
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


async def update_treatment(treatment_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    auth = _auth_headers_params()
    url = f"{settings.ns_url}/api/v1/treatments/{treatment_id}.json"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.put(url, json=patch, params=auth["params"], headers=auth["headers"])
        response.raise_for_status()
        return response.json()
