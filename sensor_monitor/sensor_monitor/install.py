import frappe


def after_install() -> None:
	for role in ("Sensor Manager", "Sensor Viewer"):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
	if not frappe.db.exists("Sensor Monitor Settings", "Sensor Monitor Settings"):
		doc = frappe.new_doc("Sensor Monitor Settings")
		doc.poll_interval_seconds = 60
		doc.snmp_timeout_seconds = 5
		doc.reading_retention_days = 90
		doc.insert(ignore_permissions=True)

	_set_desktop_icon()
	frappe.db.commit()


def _set_desktop_icon() -> None:
	if not frappe.db.exists("Desktop Icon", {"label": "Sensor Monitor"}):
		return
	frappe.db.set_value(
		"Desktop Icon",
		{"label": "Sensor Monitor"},
		{
			"app": "sensor_monitor",
			"logo_url": "/assets/sensor_monitor/images/sensor_monitor_logo.svg",
		},
	)
