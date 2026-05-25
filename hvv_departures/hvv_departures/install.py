import frappe

LOGO = "/assets/hvv_departures/images/hvv_departures_logo.svg"


def after_install() -> None:
    _set_desktop_icon()
    frappe.db.commit()


def _set_desktop_icon() -> None:
    if not frappe.db.exists("Desktop Icon", {"label": "HVV Departures"}):
        frappe.get_doc({
            "doctype": "Desktop Icon",
            "label": "HVV Departures",
            "module_name": "HVV Departures",
            "app": "hvv_departures",
            "icon_type": "App",
            "link": "/app/hvv-departures",
            "logo_url": LOGO,
            "standard": 0,
            "hidden": 0,
        }).insert(ignore_permissions=True)
        return
    frappe.db.set_value(
        "Desktop Icon",
        {"label": "HVV Departures"},
        {"app": "hvv_departures", "logo_url": LOGO, "link": "/app/hvv-departures", "icon_type": "App"},
    )
