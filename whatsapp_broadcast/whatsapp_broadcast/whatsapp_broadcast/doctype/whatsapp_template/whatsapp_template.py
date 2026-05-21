import re

import frappe
from frappe.model.document import Document

NAME_RE = re.compile(r"^[a-z0-9_]+$")
VAR_RE = re.compile(r"\{\{(\d+)\}\}")


class WhatsAppTemplate(Document):
    def validate(self):
        if not NAME_RE.match(self.template_name or ""):
            frappe.throw("template_name must match [a-z0-9_]+ (Meta requirement)")
        if len(self.body_text or "") > 1024:
            frappe.throw("body_text must be <= 1024 chars")
        if self.footer_text and len(self.footer_text) > 60:
            frappe.throw("footer_text must be <= 60 chars")
        if self.header_type == "text" and self.header_content and len(self.header_content) > 60:
            frappe.throw("header text must be <= 60 chars")
        self.variable_count = self._compute_variable_count()

    def _compute_variable_count(self) -> int:
        nums = {int(m) for m in VAR_RE.findall(self.body_text or "")}
        return max(nums) if nums else 0
