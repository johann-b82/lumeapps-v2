import frappe
from frappe.model.document import Document


class HVVSettings(Document):
    pass


def get_settings() -> "HVVSettings":
    return frappe.get_single("HVV Settings")
