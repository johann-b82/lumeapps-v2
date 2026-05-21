from __future__ import annotations
import json, re
import frappe
from frappe.model.document import Document

VAR_RE = re.compile(r"\{\{(\d+)\}\}")


class WhatsAppPost(Document):
    def before_insert(self):
        if not self.created_by:
            self.created_by = frappe.session.user

    def validate(self):
        try:
            json.loads(self.variable_values or "{}")
        except ValueError:
            frappe.throw("variable_values must be valid JSON")


def validate_for_send(post: WhatsAppPost) -> None:
    tpl = frappe.get_doc("WhatsApp Template", post.template)
    if tpl.meta_status != "approved":
        frappe.throw(f"Template {tpl.name} not approved (status={tpl.meta_status})")
    needed = {int(m) for m in VAR_RE.findall(tpl.body_text or "")}
    provided = {int(k) for k in json.loads(post.variable_values or "{}").keys()}
    if needed - provided:
        frappe.throw(f"Missing variable values: {sorted(needed - provided)}")
    if tpl.header_type in ("image", "video", "document") and not post.media_attachment:
        frappe.throw(f"Template header type {tpl.header_type} requires media_attachment")


def expand_recipients(post_name: str) -> tuple[list, int]:
    """Return (opted_in_recipient_docs, skipped_opt_out_count)."""
    post = frappe.get_doc("WhatsApp Post", post_name)
    candidate_names: set[str] = set()
    if post.recipient_mode == "by_tags":
        tags = [t.tag for t in (post.recipient_tags or [])]
        if tags:
            rows = frappe.db.sql(
                """SELECT DISTINCT r.name
                     FROM `tabWhatsApp Recipient` r
                     JOIN `tabWhatsApp Recipient Tag` rt ON rt.parent = r.name
                    WHERE rt.tag IN %(tags)s""",
                {"tags": tuple(tags)},
                as_dict=True,
            )
            candidate_names = {row.name for row in rows}
    else:
        candidate_names = {r.recipient for r in (post.explicit_recipients or [])}

    docs = [frappe.get_doc("WhatsApp Recipient", n) for n in candidate_names]
    opted = [d for d in docs if d.opt_in_status == "opted_in"]
    skipped = len(docs) - len(opted)
    return opted, skipped
