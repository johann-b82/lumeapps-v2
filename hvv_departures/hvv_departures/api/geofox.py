"""Geofox GTI signed HTTP client.

Auth: HMAC-SHA1 over the JSON request body, base64-encoded, sent in
the ``geofox-auth-signature`` header alongside ``geofox-auth-user``
and ``geofox-auth-type: HmacSHA1``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from typing import Any

import frappe
import requests

from hvv_departures.hvv_departures.doctype.hvv_settings.hvv_settings import get_settings

DEFAULT_TIMEOUT = 15


def _sign(password: str, body: bytes) -> str:
    digest = hmac.new(password.encode("utf-8"), body, hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    password = settings.get_password("password")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "geofox-auth-user": settings.username,
        "geofox-auth-type": "HmacSHA1",
        "geofox-auth-signature": _sign(password, body),
    }
    url = settings.base_url.rstrip("/") + path
    resp = requests.post(url, data=body, headers=headers, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# -- API methods --------------------------------------------------------------

INIT = {"version": 51, "language": "de"}


def init() -> dict[str, Any]:
    return _post("/gti/public/init", INIT)


def check_name(name: str, max_list: int = 20) -> dict[str, Any]:
    return _post("/gti/public/checkName", {**INIT, "theName": {"name": name}, "maxList": max_list})


def list_stations() -> dict[str, Any]:
    """Full station list incl. WGS84 coordinates. Large payload. Cache aggressively."""
    return _post("/gti/public/listStations", {**INIT, "coordinateType": "EPSG_4326"})


def departure_list(station_id: str, max_results: int = 20, max_time_offset: int | None = None) -> dict[str, Any]:
    from datetime import datetime
    if max_time_offset is None:
        max_time_offset = int(get_settings().time_horizon_minutes or 120)
    now = datetime.now()
    payload = {
        **INIT,
        "station": {"id": station_id, "type": "STATION"},
        "time": {"date": now.strftime("%d.%m.%Y"), "time": now.strftime("%H:%M")},
        "maxList": int(max_results),
        "maxTimeOffset": int(max_time_offset),
        "useRealtime": True,
    }
    return _post("/gti/public/departureList", payload)


# -- Geo helpers --------------------------------------------------------------

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def sync_stations(force: bool = False) -> dict[str, int]:
    """Pull stations within HVV Settings center+radius. Delete all outside.

    Returns ``{"synced": <upserted>, "deleted": <removed_outside>}``.
    """
    settings = get_settings()
    center_lat = float(settings.center_lat)
    center_lon = float(settings.center_lon)
    radius_m = int(settings.radius_m)

    data = list_stations()
    stations = data.get("stations", []) or []

    kept_ids: set[str] = set()
    synced = 0
    for s in stations:
        coord = s.get("coordinate") or {}
        lat, lon = coord.get("y"), coord.get("x")
        if lat is None or lon is None:
            continue
        stop_id = s.get("id")
        if not stop_id:
            continue
        if haversine_m(center_lat, center_lon, lat, lon) > radius_m:
            continue
        existing = frappe.db.exists("HVV Stop", stop_id)
        doc = frappe.get_doc("HVV Stop", stop_id) if existing else frappe.new_doc("HVV Stop")
        doc.update({
            "stop_id": stop_id,
            "stop_name": s.get("name") or stop_id,
            "city": s.get("city"),
            "combined_name": s.get("combinedName"),
            "lat": lat,
            "lon": lon,
            "type": s.get("type"),
            "vehicle_types": ",".join(s.get("vehicleTypes") or []),
            "last_synced": frappe.utils.now_datetime(),
        })
        doc.save(ignore_permissions=True)
        kept_ids.add(stop_id)
        synced += 1

    # Bulk cleanup outside radius via SQL (fast, no per-row hooks)
    before = frappe.db.count("HVV Stop")
    if kept_ids:
        placeholders = ",".join(["%s"] * len(kept_ids))
        frappe.db.sql(
            f"DELETE FROM `tabHVV Stop` WHERE name NOT IN ({placeholders})",
            tuple(kept_ids),
        )
    else:
        frappe.db.sql("DELETE FROM `tabHVV Stop`")
    frappe.db.commit()
    remaining = frappe.db.count("HVV Stop")
    return {"synced": synced, "deleted": max(0, before - remaining), "remaining": remaining}
