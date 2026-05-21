from __future__ import annotations
import json, time
import frappe
from whatsapp_broadcast.api import meta_client
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import (
    expand_recipients, validate_for_send,
)
from whatsapp_broadcast.tasks.token_bucket import TokenBucket


def _bucket(rate: int) -> TokenBucket:
    return TokenBucket(key="global", capacity=rate, refill_per_sec=rate)


def _build_components(tpl, post, recipient) -> list[dict]:
    comps = []
    vars_ = json.loads(post.variable_values or "{}")
    if tpl.header_type in ("image", "video", "document"):
        media_id = post.media_id_cache
        comps.append({
            "type": "header",
            "parameters": [{"type": tpl.header_type, tpl.header_type: {"id": media_id}}],
        })
    body_params = [{"type": "text", "text": vars_[str(i)]} for i in range(1, (tpl.variable_count or 0) + 1)]
    if body_params:
        comps.append({"type": "body", "parameters": body_params})
    return comps


def _publish_progress(post_name: str) -> None:
    frappe.publish_realtime("whatsapp_post_progress", {"post": post_name}, after_commit=True)


_COUNTER_FIELDS = {"sent_count", "delivered_count", "read_count", "failed_count"}


def _bump(post_name: str, field: str) -> None:
    if field not in _COUNTER_FIELDS:
        raise ValueError(f"refusing to bump non-whitelisted field {field!r}")
    frappe.db.sql(
        f"UPDATE `tabWhatsApp Post` SET `{field}` = COALESCE(`{field}`, 0) + 1 WHERE name = %s",
        (post_name,),
    )


def send_post(post_name: str, _inline: bool = False) -> None:
    post = frappe.get_doc("WhatsApp Post", post_name)
    validate_for_send(post)

    tpl = frappe.get_doc("WhatsApp Template", post.template)
    if tpl.header_type in ("image", "video", "document") and not post.media_id_cache:
        file_doc = frappe.get_doc("File", {"file_url": post.media_attachment})
        full = file_doc.get_full_path()
        mime = {"image": "image/jpeg", "video": "video/mp4", "document": "application/pdf"}[tpl.header_type]
        post.db_set("media_id_cache", meta_client.upload_media(full, mime))

    targets, skipped = expand_recipients(post_name)
    post.db_set({
        "status": "sending", "queued_at": frappe.utils.now_datetime(),
        "total_recipients": len(targets), "skipped_opt_out_count": skipped,
        "sent_count": 0, "delivered_count": 0, "read_count": 0, "failed_count": 0,
    })

    if not targets:
        _finalize(post_name)
        return

    for r in targets:
        log = frappe.get_doc({
            "doctype": "WhatsApp Message Log", "post": post_name,
            "recipient": r.name, "phone_number": r.phone_number, "status": "queued",
        }).insert(ignore_permissions=True)
        if _inline:
            send_single(log.name)
        else:
            frappe.enqueue(
                "whatsapp_broadcast.tasks.sender.send_single",
                log_name=log.name, queue="long", timeout=120,
            )

    if _inline:
        _finalize(post_name)


def send_single(log_name: str) -> None:
    log = frappe.get_doc("WhatsApp Message Log", log_name)
    post = frappe.get_doc("WhatsApp Post", log.post)
    tpl = frappe.get_doc("WhatsApp Template", post.template)
    s = frappe.get_single("WhatsApp Settings")
    bucket = _bucket(int(s.rate_limit_per_second or 80))
    recipient = frappe.get_doc("WhatsApp Recipient", log.recipient)

    last_err = None
    attempt = 0
    for attempt in range(int(s.max_retries_5xx or 3) + 1):
        bucket.acquire()
        try:
            resp = meta_client.send_template(
                to=log.phone_number,
                template_name=tpl.template_name, lang=tpl.language,
                components=_build_components(tpl, post, recipient),
            )
            mid = resp["messages"][0]["id"]
            log.db_set({"meta_message_id": mid, "status": "sent",
                        "sent_at": frappe.utils.now_datetime(), "retry_count": attempt})
            _bump(post.name, "sent_count")
            _publish_progress(post.name)
            _finalize(post.name)
            return
        except meta_client.MetaAPIError as e:
            last_err = e
            if not e.retryable:
                break
            time.sleep(min(16, 4 ** attempt))

    log.db_set({"status": "failed",
                "error_code": str(last_err.meta_code or last_err.status_code),
                "error_message": last_err.meta_message,
                "retry_count": attempt})
    _bump(post.name, "failed_count")
    _publish_progress(post.name)
    _finalize(post.name)


def _finalize(post_name: str) -> None:
    post = frappe.get_doc("WhatsApp Post", post_name)
    if (post.sent_count or 0) + (post.failed_count or 0) < (post.total_recipients or 0):
        return
    final = "failed" if post.failed_count == post.total_recipients and post.total_recipients > 0 else "completed"
    post.db_set({"status": final, "completed_at": frappe.utils.now_datetime()})
    _publish_progress(post_name)


@frappe.whitelist()
def trigger_send(post_name: str) -> None:
    post = frappe.get_doc("WhatsApp Post", post_name)
    validate_for_send(post)
    post.db_set("status", "queued")
    frappe.enqueue(
        "whatsapp_broadcast.tasks.sender.send_post",
        post_name=post_name, queue="long", timeout=600, enqueue_after_commit=True,
    )
