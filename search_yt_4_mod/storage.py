from __future__ import annotations

import json
import os
import re

DATA_DIR = "data"
CHANNEL_STORE_PATH = os.path.join(DATA_DIR, "channels.json")
OUTPUT_DIR_DEFAULT = "추출"


def sanitize_filename(name: str, max_len: int = 150) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)
    return (name[:max_len].rstrip() or "video")


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def load_channel_store() -> dict:
    _ensure_data_dir()
    try:
        with open(CHANNEL_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("channels"), list):
                return data
    except Exception:
        pass
    return {"channels": []}


def save_channel_store(data: dict) -> None:
    _ensure_data_dir()
    with open(CHANNEL_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_channel_to_store(cid: str, title: str) -> None:
    if not cid or not cid.startswith("UC"):
        return
    data = load_channel_store()
    items = {c["id"]: c for c in data.get("channels", []) if isinstance(c, dict) and "id" in c}
    prev = items.get(cid)
    if not prev or (title and prev.get("title") != title):
        items[cid] = {"id": cid, "title": title or (prev.get("title") if prev else "")}
        data["channels"] = sorted(items.values(), key=lambda x: (x.get("title") or "").lower())
        save_channel_store(data)


def remove_channels_from_store(ids) -> None:
    data = load_channel_store()
    keep = [c for c in data.get("channels", []) if c.get("id") not in set(ids)]
    data["channels"] = keep
    save_channel_store(data)
