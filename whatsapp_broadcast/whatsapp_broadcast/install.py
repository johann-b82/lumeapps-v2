import frappe

LOGO = "/assets/whatsapp_broadcast/images/whatsapp_broadcast_logo.svg"


def after_install() -> None:
    _ensure_role("WhatsApp Manager")
    _ensure_role("WhatsApp User")
    _set_desktop_icon()
    _hide_home_workspace()
    frappe.db.commit()


def _hide_home_workspace() -> None:
    if frappe.db.exists("Workspace", "Home"):
        frappe.db.set_value("Workspace", "Home", "is_hidden", 1)


def _ensure_role(role_name: str) -> None:
    if not frappe.db.exists("Role", role_name):
        frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(
            ignore_permissions=True
        )


def _set_desktop_icon() -> None:
    if not frappe.db.exists("Desktop Icon", {"label": "WhatsApp Broadcast"}):
        frappe.get_doc({
            "doctype": "Desktop Icon",
            "label": "WhatsApp Broadcast",
            "module_name": "WhatsApp Broadcast",
            "app": "whatsapp_broadcast",
            "icon_type": "App",
            "link": "/app/whatsapp-broadcast",
            "logo_url": LOGO,
            "standard": 0,
            "hidden": 0,
        }).insert(ignore_permissions=True)
        return
    frappe.db.set_value(
        "Desktop Icon",
        {"label": "WhatsApp Broadcast"},
        {"app": "whatsapp_broadcast", "logo_url": LOGO, "link": "/app/whatsapp-broadcast", "icon_type": "App"},
    )
