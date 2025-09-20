from __future__ import annotations

import logging
from math import isclose
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.services import nightscout
from app.utils.telegram import verify_init_data
from app.utils.treatments import apply_meta_updates, parse_meta

logger = logging.getLogger("ns_webapp")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Nightscout Telegram WebApp Bridge")

settings = get_settings()
webapp_dir = Path(__file__).parent / "webapp"
app.mount("/webapp", StaticFiles(directory=webapp_dir, html=True), name="webapp")


@app.get("/healthz")
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}


def get_settings_dep() -> Settings:
    return get_settings()


@app.get("/api/treatment")
async def get_treatment(
    cid: str = Query(..., alias="cid"),
    init_data: str = Query(..., alias="initData"),
) -> Dict[str, Any]:
    verify_init_data(init_data)
    record = await nightscout.fetch_treatment_by_client_id(cid)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Treatment not found")

    meta = parse_meta(record.get("notes"))
    response = {
        "id": record.get("_id"),
        "eventType": record.get("eventType") or "None",
        "insulin": record.get("insulin"),
        "carbs": record.get("carbs"),
        "calories": record.get("calories_kcal") or meta.get("calories_kcal"),
        "protein": record.get("protein_g") or meta.get("protein_g"),
        "meal": record.get("meal") or meta.get("meal"),
        "photoUrl": record.get("photoUrl") or meta.get("photoUrl"),
        "notes": record.get("notes"),
    }
    return response


def _parse_optional_float(raw: Optional[str], field_name: str, min_value: float = 0.0, max_value: float = 10000.0) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except ValueError as exc:  # noqa: B902
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}") from exc
    if not (min_value <= value <= max_value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} out of range")
    return value


def _parse_optional_int(raw: Optional[str], field_name: str, min_value: int = 0, max_value: int = 100000) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        value = int(float(raw))
    except ValueError as exc:  # noqa: B902
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}") from exc
    if not (min_value <= value <= max_value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} out of range")
    return value


def _normalize_event_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if value.lower() == "none":
        return None
    allowed = {"Meal Bolus", "Carb Correction", "Correction Bolus", "None"}
    if value not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported eventType")
    return value


def _different(current: Any, new_value: Any) -> bool:
    if current is None and new_value is None:
        return False
    if isinstance(current, (int, float)) and isinstance(new_value, (int, float)):
        return not isclose(float(current), float(new_value), rel_tol=1e-6, abs_tol=1e-6)
    return current != new_value


@app.put("/api/treatment")
async def update_treatment(
    init_data: str = Form(..., alias="initData"),
    treatment_id: str = Form(..., alias="id"),
    cid: Optional[str] = Form(None, alias="cid"),
    event_type_raw: Optional[str] = Form(None, alias="eventType"),
    insulin_raw: Optional[str] = Form(None, alias="insulin"),
    carbs_raw: Optional[str] = Form(None, alias="carbs"),
    calories_raw: Optional[str] = Form(None, alias="calories"),
    protein_raw: Optional[str] = Form(None, alias="protein"),
    meal: Optional[str] = Form(None, alias="meal"),
    photo_url: Optional[str] = Form(None, alias="photoUrl"),
) -> Response:
    verify_init_data(init_data)

    record = await nightscout.fetch_treatment_by_id(treatment_id)
    if not record and cid:
        record = await nightscout.fetch_treatment_by_client_id(cid)
        if record:
            treatment_id = record.get("_id") or treatment_id
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Treatment not found")

    event_type = _normalize_event_type(event_type_raw)
    insulin = _parse_optional_float(insulin_raw, "insulin", 0.0, 50.0)
    carbs = _parse_optional_float(carbs_raw, "carbs", 0.0, 2000.0)
    calories = _parse_optional_int(calories_raw, "calories", 0, 100000)
    protein = _parse_optional_int(protein_raw, "protein", 0, 10000)
    meal_clean = meal.strip() if meal else None
    photo_url_clean = photo_url.strip() if photo_url else None

    patch: Dict[str, Any] = {}
    meta_updates: Dict[str, Any] = {}

    if _different(record.get("eventType"), event_type):
        patch["eventType"] = event_type

    if _different(record.get("insulin"), insulin):
        patch["insulin"] = insulin
        meta_updates["insulin_u"] = insulin

    if _different(record.get("carbs"), carbs):
        patch["carbs"] = carbs
        meta_updates["carbs_g"] = int(carbs) if carbs is not None else None

    current_calories = record.get("calories_kcal")
    if _different(current_calories, calories):
        patch["calories_kcal"] = calories
        meta_updates["calories_kcal"] = calories

    current_protein = record.get("protein_g")
    if _different(current_protein, protein):
        patch["protein_g"] = protein
        meta_updates["protein_g"] = protein

    if _different(record.get("meal"), meal_clean):
        patch["meal"] = meal_clean
        meta_updates["meal"] = meal_clean

    if _different(record.get("photoUrl"), photo_url_clean):
        patch["photoUrl"] = photo_url_clean
        meta_updates["photoUrl"] = photo_url_clean

    notes_updated = apply_meta_updates(record.get("notes"), meta_updates)
    if notes_updated != record.get("notes"):
        patch["notes"] = notes_updated

    if not patch:
        return JSONResponse({"status": "ok", "updated": False})

    target_id = record.get("_id") or treatment_id
    await nightscout.update_treatment(target_id, patch)
    return JSONResponse({"status": "ok", "updated": True})


MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


@app.post("/api/upload")
async def upload_image(
    init_data: str = Form(..., alias="initData"),
    image: UploadFile = File(..., alias="image"),
    settings: Settings = Depends(get_settings_dep),
) -> Dict[str, str]:
    verify_init_data(init_data)

    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")

    contents = await image.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")

    extension = ".jpg" if image.content_type == "image/jpeg" else ".png"
    media_root = settings.media_root
    media_root.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    import uuid

    now = datetime.utcnow()
    target_dir = media_root / f"{now.year:04d}" / f"{now.month:02d}"
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    destination = target_dir / filename

    destination.write_bytes(contents)

    relative_path = destination.relative_to(media_root)
    url = f"{settings.media_base_url}/{relative_path.as_posix()}"
    return {"url": url}
