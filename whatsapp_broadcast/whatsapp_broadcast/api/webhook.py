from __future__ import annotations
import hmac, hashlib, json
import frappe


def _settings():
    return frappe.get_single("WhatsApp Settings")


def _verify_challenge(query: dict) -> str:
    expected = _settings().get_password("webhook_verify_token")
    if query.get("hub.mode") == "subscribe" and query.get("hub.verify_token") == expected:
        return query.get("hub.challenge", "")
    raise frappe.PermissionError("verify token mismatch")


def _verify_signature(raw_body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    secret = _settings().get_password("app_secret").encode()
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle() -> str | dict:
    req = frappe.request
    if req.method == "GET":
        return _verify_challenge(req.args.to_dict())

    raw = req.get_data() or b""
    sig = req.headers.get("X-Hub-Signature-256")
    if not _verify_signature(raw, sig):
        frappe.local.response.http_status_code = 403
        frappe.logger().warning("whatsapp webhook: bad signature")
        return {"ok": False}

    payload = json.loads(raw.decode() or "{}")
    _process(payload)
    return {"ok": True}


def _process(payload: dict) -> None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            for status in value.get("statuses", []) or []:
                _apply_status(status)


def _apply_status(status: dict) -> None:
    mid = status.get("id")
    if not mid:
        return
    log_name = frappe.db.get_value("WhatsApp Message Log", {"meta_message_id": mid}, "name")
    if not log_name:
        return
    log = frappe.get_doc("WhatsApp Message Log", log_name)
    new_status = (status.get("status") or "").lower()
    ts = frappe.utils.get_datetime_str(frappe.utils.get_datetime(int(status.get("timestamp", "0"))))
    if new_status == "sent":
        log.db_set({"status": "sent", "sent_at": ts})
    elif new_status == "delivered":
        log.db_set({"status": "delivered", "delivered_at": ts})
        _bump_counter(log.post, "delivered_count")
    elif new_status == "read":
        log.db_set({"status": "read", "read_at": ts})
        _bump_counter(log.post, "read_count")
    elif new_status == "failed":
        err = (status.get("errors") or [{}])[0]
        log.db_set({"status": "failed", "error_code": str(err.get("code", "")), "error_message": err.get("message", "")})
        _bump_counter(log.post, "failed_count")
    log.db_set("raw_webhook_payload", json.dumps(status))


_COUNTER_FIELDS = {"sent_count", "delivered_count", "read_count", "failed_count"}


def _bump_counter(post_name: str, field: str) -> None:
    if field not in _COUNTER_FIELDS:
        raise ValueError(f"refusing to bump non-whitelisted field {field!r}")
    frappe.db.sql(
        f"UPDATE `tabWhatsApp Post` SET `{field}` = COALESCE(`{field}`, 0) + 1 WHERE name = %s",
        (post_name,),
    )
