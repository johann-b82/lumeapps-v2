import hmac, hashlib
import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.api import webhook


class TestWebhookSignature(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        s = frappe.get_single("WhatsApp Settings")
        s.phone_number_id = "111"; s.business_account_id = "222"
        s.access_token = "TOKEN"; s.webhook_verify_token = "VT"; s.app_secret = "SECRET"
        s.save(ignore_permissions=True); frappe.db.commit()

    def test_verify_challenge_returns_challenge(self):
        result = webhook._verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "VT", "hub.challenge": "C123"})
        self.assertEqual(result, "C123")

    def test_verify_challenge_wrong_token_raises(self):
        with self.assertRaises(frappe.PermissionError):
            webhook._verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "C"})

    def test_verify_signature_valid(self):
        body = b'{"x":1}'
        sig = "sha256=" + hmac.new(b"SECRET", body, hashlib.sha256).hexdigest()
        self.assertTrue(webhook._verify_signature(body, sig))

    def test_verify_signature_invalid(self):
        self.assertFalse(webhook._verify_signature(b'{"x":1}', "sha256=deadbeef"))

    def test_verify_signature_missing(self):
        self.assertFalse(webhook._verify_signature(b'{}', None))


import json
from unittest.mock import patch


class TestWebhookStatusFlow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        s = frappe.get_single("WhatsApp Settings")
        s.app_secret = "SECRET"; s.webhook_verify_token = "VT"
        s.save(ignore_permissions=True); frappe.db.commit()

    def test_delivered_status_updates_log_and_post(self):
        if not frappe.db.exists("WhatsApp Template", "wh_tpl"):
            frappe.get_doc({"doctype": "WhatsApp Template", "template_name": "wh_tpl",
                            "language": "de", "category": "MARKETING",
                            "header_type": "none", "body_text": "x",
                            "meta_status": "approved"}).insert(ignore_permissions=True)
        if not frappe.db.exists("WhatsApp Recipient", "+491702222201"):
            frappe.get_doc({"doctype": "WhatsApp Recipient", "recipient_name": "W",
                            "phone_number": "+491702222201", "opt_in_status": "opted_in"}).insert(ignore_permissions=True)
        post = frappe.get_doc({"doctype": "WhatsApp Post", "title": "wh1",
                               "template": "wh_tpl", "variable_values": "{}",
                               "recipient_mode": "explicit_list",
                               "explicit_recipients": [{"recipient": "+491702222201"}],
                               "total_recipients": 1}).insert(ignore_permissions=True)
        log = frappe.get_doc({"doctype": "WhatsApp Message Log", "post": post.name,
                              "recipient": "+491702222201", "phone_number": "+491702222201",
                              "status": "sent", "meta_message_id": "wamid.WH1"}).insert(ignore_permissions=True)

        payload = {"entry": [{"changes": [{"value": {"statuses": [
            {"id": "wamid.WH1", "status": "delivered", "timestamp": "1716220800"}
        ]}}]}]}
        raw = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(b"SECRET", raw, hashlib.sha256).hexdigest()

        from werkzeug.wrappers import Request
        from werkzeug.test import EnvironBuilder
        env = EnvironBuilder(method="POST", data=raw,
                             headers={"X-Hub-Signature-256": sig,
                                      "Content-Type": "application/json"}).get_environ()
        prev = getattr(frappe.local, "request", None)
        frappe.local.request = Request(env)
        try:
            from whatsapp_broadcast.api.webhook import handle
            result = handle()
        finally:
            if prev is None:
                try: del frappe.local.request
                except AttributeError: pass
            else:
                frappe.local.request = prev
        self.assertEqual(result, {"ok": True})
        post.reload(); log.reload()
        self.assertEqual(log.status, "delivered")
        self.assertEqual(post.delivered_count, 1)
