import frappe
from frappe.model.document import Document


class WhatsAppMessageLog(Document):
    pass


def on_doctype_update():
    frappe.db.add_index("WhatsApp Message Log", ["meta_message_id"])
