import frappe


def after_install():
    _ensure_role("WhatsApp Manager")
    _ensure_role("WhatsApp User")
    frappe.db.commit()


def _ensure_role(role_name: str) -> None:
    if not frappe.db.exists("Role", role_name):
        frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(
            ignore_permissions=True
        )
