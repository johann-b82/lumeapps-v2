import frappe
from frappe.model.document import Document


class WhatsAppSettings(Document):
    pass


def get_settings() -> "WhatsAppSettings":
    return frappe.get_single("WhatsApp Settings")
