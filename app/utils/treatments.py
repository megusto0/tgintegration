from __future__ import annotations

import json
from typing import Any, Dict

META_PREFIX = "[alice-meta]"


def parse_meta(notes: str | None) -> Dict[str, Any]:
    if not notes or not notes.startswith(META_PREFIX):
        return {}
    payload = notes[len(META_PREFIX) :]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


def apply_meta_updates(notes: str | None, updates: Dict[str, Any]) -> str | None:
    if not updates:
        return notes

    meta = parse_meta(notes)
    if not meta and not notes:
        # create new meta shell when notes were missing
        meta = {"ver": 1}

    if not meta:
        # do not overwrite non-meta notes
        return notes

    for key, value in updates.items():
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value

    return META_PREFIX + json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
