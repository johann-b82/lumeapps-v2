"""SNMP polling task for the sensor_monitor app.

Scheduled by Frappe's `scheduler_events` in hooks.py. Each tick:
 1. read poll_interval_seconds from Sensor Monitor Settings
 2. iterate enabled Sensor rows
 3. SNMP GET temperature_oid and humidity_oid via pysnmp
 4. write Sensor Reading + Sensor Poll Log rows
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import frappe
from frappe.utils import get_datetime_str, now_datetime


def _snmp_get(host: str, port: int, community: str, oid: str, timeout: int) -> tuple[Any, str | None]:
	"""Return (value, error_kind). Uses pysnmp; lazy import so the app loads
	even when pysnmp isn't installed yet."""
	import asyncio
	try:
		from pysnmp.hlapi.v1arch.asyncio import (
			CommunityData,
			ObjectIdentity,
			ObjectType,
			SnmpDispatcher,
			UdpTransportTarget,
			get_cmd,
		)
	except ImportError:
		return None, "pysnmp_missing"

	async def _run():
		target = await UdpTransportTarget.create(
			(host, port), timeout=timeout, retries=1
		)
		return await get_cmd(
			SnmpDispatcher(),
			CommunityData(community, mpModel=0),
			target,
			ObjectType(ObjectIdentity(oid)),
		)

	err_indication, err_status, _err_index, var_binds = asyncio.run(_run())
	if err_indication:
		return None, f"snmp:{err_indication}"
	if err_status:
		return None, f"snmp:{err_status.prettyPrint()}"
	if not var_binds:
		return None, "snmp:no_varbinds"
	return var_binds[0][1], None


def _to_decimal(raw: Any, scale: float | Decimal) -> float | None:
	if raw is None:
		return None
	try:
		return float(raw) * float(scale or 1.0)
	except (TypeError, ValueError):
		return None


def poll_sensor(sensor_name: str) -> dict:
	"""Poll one sensor immediately and persist reading + log row."""
	sensor = frappe.get_doc("Sensor", sensor_name)
	settings = frappe.get_single("Sensor Monitor Settings")
	timeout = int(settings.snmp_timeout_seconds or 5)

	if not sensor.enabled:
		return {"sensor": sensor_name, "skipped": "disabled"}

	community = sensor.get_password("community", raise_exception=False) or ""
	t0 = time.monotonic()
	error_kind: str | None = None
	temperature = humidity = None

	if sensor.temperature_oid:
		raw, err = _snmp_get(sensor.host, sensor.port, community, sensor.temperature_oid, timeout)
		if err:
			error_kind = err
		else:
			temperature = _to_decimal(raw, sensor.temperature_scale)
	if sensor.humidity_oid and not error_kind:
		raw, err = _snmp_get(sensor.host, sensor.port, community, sensor.humidity_oid, timeout)
		if err:
			error_kind = err
		else:
			humidity = _to_decimal(raw, sensor.humidity_scale)

	latency_ms = int((time.monotonic() - t0) * 1000)
	now = get_datetime_str(now_datetime())
	success = error_kind is None and (temperature is not None or humidity is not None)

	# Raw SQL insert avoids Frappe DateTime cast that injects a +00:00 TZ
	# (incompatible with MariaDB's DATETIME column).
	pl_name = frappe.generate_hash(length=10)
	frappe.db.sql(
		"""INSERT INTO `tabSensor Poll Log`
		   (name, creation, modified, modified_by, owner, docstatus, idx,
		    sensor, attempted_at, success, error_kind, latency_ms)
		   VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, %s)""",
		(pl_name, now, now, "Administrator", "Administrator",
		 sensor.name, now, 1 if success else 0, error_kind, latency_ms),
	)

	if success:
		sr_name = frappe.generate_hash(length=10)
		frappe.db.sql(
			"""INSERT INTO `tabSensor Reading`
			   (name, creation, modified, modified_by, owner, docstatus, idx,
			    sensor, recorded_at, temperature, humidity, error_code)
			   VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, NULL)""",
			(sr_name, now, now, "Administrator", "Administrator",
			 sensor.name, now, temperature, humidity),
		)

	frappe.db.commit()
	return {
		"sensor": sensor.name,
		"success": success,
		"temperature": temperature,
		"humidity": humidity,
		"error_kind": error_kind,
		"latency_ms": latency_ms,
	}


def poll_all() -> list[dict]:
	"""Scheduled entry point — poll every enabled sensor."""
	results = []
	for row in frappe.get_all("Sensor", filters={"enabled": 1}, pluck="name"):
		try:
			results.append(poll_sensor(row))
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"sensor_monitor poll_all: {row}")
			results.append({"sensor": row, "success": False, "error_kind": f"exception:{e!r}"})
	return results


def purge_old_readings() -> int:
	"""Daily cleanup. Removes readings older than retention_days."""
	settings = frappe.get_single("Sensor Monitor Settings")
	days = int(settings.reading_retention_days or 0)
	if days <= 0:
		return 0
	cutoff = frappe.utils.add_days(frappe.utils.now_datetime(), -days)
	deleted = frappe.db.sql(
		"DELETE FROM `tabSensor Reading` WHERE recorded_at < %s", (cutoff,)
	)
	frappe.db.sql(
		"DELETE FROM `tabSensor Poll Log` WHERE attempted_at < %s", (cutoff,)
	)
	frappe.db.commit()
	return deleted or 0
