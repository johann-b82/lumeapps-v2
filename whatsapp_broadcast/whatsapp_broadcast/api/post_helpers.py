import json
import frappe
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import (
    expand_recipients,
)


@frappe.whitelist()
def preview(post_name: str) -> dict:
    post = frappe.get_doc("WhatsApp Post", post_name)
    tpl = frappe.get_doc("WhatsApp Template", post.template)
    vars_ = json.loads(post.variable_values or "{}")
    body = tpl.body_text or ""
    for k, v in vars_.items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    return {
        "header_type": tpl.header_type,
        "header_content": tpl.header_content,
        "body": body,
        "footer": tpl.footer_text,
        "buttons": [{"type": b.button_type, "text": b.text} for b in (tpl.buttons or [])],
    }


@frappe.whitelist()
def recipient_count(post_name: str) -> dict:
    targets, skipped = expand_recipients(post_name)
    return {"total": len(targets), "skipped_opt_out": skipped}
