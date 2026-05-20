"""Whitelisted REST API for the sensor dashboard frontend."""
from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from sensor_monitor.sensor_monitor.poller import poll_sensor


WINDOWS = {
	"1h":  ("hours", -1),
	"6h":  ("hours", -6),
	"24h": ("hours", -24),
	"7d":  ("days",  -7),
	"30d": ("days",  -30),
}


def _window_to_cutoff(window: str):
	unit, val = WINDOWS.get(window, ("hours", -24))
	return add_to_date(now_datetime(), **{unit: val})


@frappe.whitelist()
def list_sensors() -> list[dict]:
	return frappe.get_all(
		"Sensor",
		fields=[
			"name", "sensor_name", "host", "port", "enabled", "chart_color",
		],
		order_by="sensor_name asc",
	)


@frappe.whitelist()
def get_settings() -> dict:
	"""Return global thresholds + poll interval for the dashboard UI."""
	s = frappe.get_single("Sensor Monitor Settings")
	return {
		"global_temperature_min": s.global_temperature_min,
		"global_temperature_max": s.global_temperature_max,
		"global_humidity_min":    s.global_humidity_min,
		"global_humidity_max":    s.global_humidity_max,
		"poll_interval_seconds":  s.poll_interval_seconds,
	}


@frappe.whitelist()
def get_readings(sensor: str, window: str = "24h") -> dict:
	cutoff = _window_to_cutoff(window)
	rows = frappe.get_all(
		"Sensor Reading",
		filters={"sensor": sensor, "recorded_at": [">=", cutoff]},
		fields=["recorded_at", "temperature", "humidity"],
		order_by="recorded_at asc",
		limit_page_length=0,
	)
	return {"sensor": sensor, "window": window, "rows": rows}


@frappe.whitelist()
def get_latest(sensor: str) -> dict | None:
	rows = frappe.get_all(
		"Sensor Reading",
		filters={"sensor": sensor},
		fields=["recorded_at", "temperature", "humidity"],
		order_by="recorded_at desc",
		limit_page_length=1,
	)
	if not rows:
		return None
	return rows[0]


@frappe.whitelist()
def health(sensor: str) -> dict:
	"""Return 'OK since X' or 'Offline since X min' summary for one sensor."""
	last_success = frappe.db.sql(
		"""SELECT attempted_at FROM `tabSensor Poll Log`
		   WHERE sensor=%s AND success=1
		   ORDER BY attempted_at DESC LIMIT 1""",
		sensor,
	)
	last_attempt = frappe.db.sql(
		"""SELECT attempted_at, error_kind FROM `tabSensor Poll Log`
		   WHERE sensor=%s ORDER BY attempted_at DESC LIMIT 1""",
		sensor,
	)
	return {
		"sensor": sensor,
		"last_success": last_success[0][0].isoformat() if last_success else None,
		"last_attempt": last_attempt[0][0].isoformat() if last_attempt else None,
		"last_error": last_attempt[0][1] if last_attempt and last_attempt[0][1] else None,
	}


@frappe.whitelist()
def poll_now(sensor: str) -> dict:
	"""Trigger an immediate SNMP poll for one sensor."""
	frappe.only_for(["System Manager", "Sensor Manager"])
	return poll_sensor(sensor)


@frappe.whitelist()
def probe(host: str, port: int, community: str, oid: str, timeout: int = 5) -> dict:
	"""SNMP GET against an arbitrary host/oid for the discovery UI."""
	frappe.only_for(["System Manager", "Sensor Manager"])
	from sensor_monitor.sensor_monitor.poller import _snmp_get
	val, err = _snmp_get(host, int(port or 161), community, oid, int(timeout))
	return {"value": str(val) if val is not None else None, "error": err}
