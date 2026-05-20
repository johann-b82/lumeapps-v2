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
	frappe.db.commit()
