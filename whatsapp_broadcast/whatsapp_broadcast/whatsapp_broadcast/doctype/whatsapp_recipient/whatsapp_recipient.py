import re

import frappe
from frappe.model.document import Document

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class WhatsAppRecipient(Document):
    def validate(self):
        if not E164.match(self.phone_number or ""):
            frappe.throw("phone_number must be E.164 format, e.g. +491701234567")
        if self.opt_in_status == "opted_in" and not self.opt_in_date:
            self.opt_in_date = frappe.utils.now_datetime()
