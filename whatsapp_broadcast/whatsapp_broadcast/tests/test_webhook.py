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
