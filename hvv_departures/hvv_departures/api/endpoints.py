"""Whitelisted endpoints for the HVV Departures Desk page."""

from __future__ import annotations

from typing import Any

import frappe

from hvv_departures.api import geofox
from hvv_departures.hvv_departures.doctype.hvv_settings.hvv_settings import get_settings


@frappe.whitelist()
def test_connection() -> dict[str, Any]:
    """Ping Geofox /init endpoint to validate credentials + connectivity."""
    s = get_settings()
    if not s.username or not s.get_password("password"):
        return {"ok": False, "error": "Username/Password missing in HVV Settings."}
    try:
        data = geofox.init()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    rc = (data.get("returnCode") or "").upper()
    return {
        "ok": rc == "OK",
        "return_code": rc or None,
        "build": data.get("buildText") or data.get("build"),
        "version": data.get("version"),
        "begin_of_service": data.get("beginOfService"),
        "end_of_service": data.get("endOfService"),
        "error": None if rc == "OK" else (data.get("errorText") or "Non-OK return code"),
    }


@frappe.whitelist()
def get_center() -> dict[str, Any]:
    s = get_settings()
    return {
        "lat": s.center_lat,
        "lon": s.center_lon,
        "radius_m": s.radius_m,
    }


@frappe.whitelist()
def sync_stations() -> dict[str, Any]:
    return geofox.sync_stations()


@frappe.whitelist()
def nearby_stations(
    lat: float | None = None,
    lon: float | None = None,
    radius_m: int | None = None,
) -> list[dict[str, Any]]:
    s = get_settings()
    lat = float(lat if lat is not None else s.center_lat)
    lon = float(lon if lon is not None else s.center_lon)
    radius_m = int(radius_m if radius_m is not None else s.radius_m)

    if not frappe.db.count("HVV Stop"):
        geofox.sync_stations()

    rows = frappe.get_all(
        "HVV Stop",
        fields=["stop_id", "stop_name", "combined_name", "city", "lat", "lon", "type", "vehicle_types", "lines_cache"],
        limit_page_length=0,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["lat"] is None or r["lon"] is None:
            continue
        d = geofox.haversine_m(lat, lon, r["lat"], r["lon"])
        if d <= radius_m:
            r["distance_m"] = round(d, 1)
            out.append(r)
    out.sort(key=lambda x: x["distance_m"])
    return out


@frappe.whitelist()
def departures(station_id: str, max_results: int = 20, max_time_offset: int | None = None) -> dict[str, Any]:
    return geofox.departure_list(
        station_id,
        int(max_results),
        int(max_time_offset) if max_time_offset is not None else None,
    )


@frappe.whitelist()
def geocode_address(query: str, max_list: int = 10) -> list[dict[str, Any]]:
    """Resolve free-text address to coordinate candidates via Geofox checkName."""
    data = geofox.check_name(query, max_list=int(max_list))
    results = data.get("results") or []
    out = []
    for r in results:
        coord = r.get("coordinate") or {}
        if coord.get("y") is None or coord.get("x") is None:
            continue
        out.append({
            "name": r.get("name"),
            "city": r.get("city"),
            "combined_name": r.get("combinedName"),
            "type": r.get("type"),
            "lat": coord.get("y"),
            "lon": coord.get("x"),
        })
    return out


def _line_summary(station_id: str) -> str:
    """Distinct line names for a station (cached via departureList)."""
    try:
        data = geofox.departure_list(station_id, max_results=30)
    except Exception:
        return ""
    seen: dict[str, str] = {}
    for d in (data.get("departures") or []):
        line = d.get("line") or {}
        name = line.get("name")
        if not name:
            continue
        direction = line.get("direction") or ""
        seen.setdefault(name, direction)
    return "; ".join(f"{n} → {d}" if d else n for n, d in seen.items())


@frappe.whitelist()
def nearby_with_lines(
    lat: float | None = None,
    lon: float | None = None,
    radius_m: int | None = None,
    refresh_lines: int = 1,
) -> list[dict[str, Any]]:
    """Stops within radius incl. line summary. Uses cached HVV Stop list."""
    if not frappe.db.count("HVV Stop"):
        geofox.sync_stations()

    s = get_settings()
    lat = float(lat if lat is not None else s.center_lat)
    lon = float(lon if lon is not None else s.center_lon)
    radius_m = int(radius_m if radius_m is not None else s.radius_m)
    refresh_lines = int(refresh_lines)

    rows = frappe.get_all(
        "HVV Stop",
        fields=["stop_id", "stop_name", "combined_name", "city", "lat", "lon", "type",
                "vehicle_types", "lines_cache"],
        limit_page_length=0,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["lat"] is None or r["lon"] is None:
            continue
        d = geofox.haversine_m(lat, lon, r["lat"], r["lon"])
        if d > radius_m:
            continue
        r["distance_m"] = round(d, 1)
        if refresh_lines and not r.get("lines_cache"):
            r["lines_cache"] = _line_summary(r["stop_id"])
            frappe.db.set_value("HVV Stop", r["stop_id"], "lines_cache", r["lines_cache"])
        out.append(r)
    out.sort(key=lambda x: x["distance_m"])
    return out


@frappe.whitelist()
def search_stops(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Autocomplete search over cached HVV Stop by name/city/id."""
    query = (query or "").strip()
    limit = int(limit)
    filters = {}
    if query:
        like = f"%{query}%"
        rows = frappe.db.sql(
            """
            SELECT stop_id, stop_name, city, combined_name, lat, lon, type
            FROM `tabHVV Stop`
            WHERE stop_name LIKE %(q)s OR city LIKE %(q)s OR combined_name LIKE %(q)s OR stop_id LIKE %(q)s
            ORDER BY stop_name ASC
            LIMIT %(lim)s
            """,
            {"q": like, "lim": limit},
            as_dict=True,
        )
    else:
        rows = frappe.get_all(
            "HVV Stop",
            fields=["stop_id", "stop_name", "city", "combined_name", "lat", "lon", "type"],
            order_by="stop_name asc",
            limit_page_length=limit,
        )
    return rows
