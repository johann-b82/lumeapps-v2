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


from whatsapp_broadcast.api import meta_client


def _build_components(doc: "WhatsAppTemplate") -> list[dict]:
    comps = []
    if doc.header_type == "text" and doc.header_content:
        comps.append({"type": "HEADER", "format": "TEXT", "text": doc.header_content})
    elif doc.header_type in ("image", "video", "document"):
        comps.append({"type": "HEADER", "format": doc.header_type.upper()})
    comps.append({"type": "BODY", "text": doc.body_text})
    if doc.footer_text:
        comps.append({"type": "FOOTER", "text": doc.footer_text})
    if doc.buttons:
        comps.append({
            "type": "BUTTONS",
            "buttons": [_button_payload(b) for b in doc.buttons],
        })
    return comps


def _button_payload(b) -> dict:
    if b.button_type == "quick_reply":
        return {"type": "QUICK_REPLY", "text": b.text}
    if b.button_type == "url":
        return {"type": "URL", "text": b.text, "url": b.url_or_phone}
    return {"type": "PHONE_NUMBER", "text": b.text, "phone_number": b.url_or_phone}


@frappe.whitelist()
def submit_to_meta(name: str) -> None:
    doc = frappe.get_doc("WhatsApp Template", name)
    payload = {
        "name": doc.template_name,
        "language": doc.language,
        "category": doc.category,
        "components": _build_components(doc),
    }
    resp = meta_client.submit_template(payload)
    doc.db_set("meta_template_id", resp.get("id"))
    doc.db_set("meta_status", "pending")


@frappe.whitelist()
def sync_status(name: str) -> None:
    doc = frappe.get_doc("WhatsApp Template", name)
    info = meta_client.get_template_status(doc.template_name, doc.language)
    status = (info.get("status") or "").lower()
    if status in ("local", "pending", "approved", "rejected", "paused"):
        doc.db_set("meta_status", status)
    if status == "rejected":
        doc.db_set("rejection_reason", info.get("rejected_reason", ""))
