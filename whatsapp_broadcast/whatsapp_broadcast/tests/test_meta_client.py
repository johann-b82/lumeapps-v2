import json
import responses
from frappe.tests.utils import FrappeTestCase
import frappe
from whatsapp_broadcast.api import meta_client


def _set_settings():
    s = frappe.get_single("WhatsApp Settings")
    s.phone_number_id = "111"
    s.business_account_id = "222"
    s.access_token = "TOKEN"
    s.webhook_verify_token = "VT"
    s.app_secret = "SECRET"
    s.default_language = "de"
    s.rate_limit_per_second = 80
    s.max_retries_5xx = 3
    s.save(ignore_permissions=True)
    frappe.db.commit()


class TestMetaClient(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _set_settings()

    @responses.activate
    def test_send_template_success_returns_message_id(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.ABC"}]},
            status=200,
        )
        resp = meta_client.send_template(
            to="+491701234567",
            template_name="hello_world",
            lang="de",
            components=[],
        )
        self.assertEqual(resp["messages"][0]["id"], "wamid.ABC")
        body = json.loads(responses.calls[0].request.body)
        self.assertEqual(body["to"], "+491701234567")
        self.assertEqual(body["template"]["name"], "hello_world")
        self.assertEqual(
            responses.calls[0].request.headers["Authorization"], "Bearer TOKEN"
        )

    @responses.activate
    def test_send_template_4xx_raises_metaapierror_no_retry(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 132000, "message": "Template not approved"}},
            status=400,
        )
        with self.assertRaises(meta_client.MetaAPIError) as cm:
            meta_client.send_template(to="+491701234567", template_name="x", lang="de", components=[])
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.meta_code, 132000)
        self.assertFalse(cm.exception.retryable)

    @responses.activate
    def test_send_template_5xx_marks_retryable(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 1, "message": "boom"}},
            status=503,
        )
        with self.assertRaises(meta_client.MetaAPIError) as cm:
            meta_client.send_template(to="+491701234567", template_name="x", lang="de", components=[])
        self.assertTrue(cm.exception.retryable)

    @responses.activate
    def test_send_template_429_marks_retryable(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 80007, "message": "rate"}},
            status=429,
        )
        with self.assertRaises(meta_client.MetaAPIError) as cm:
            meta_client.send_template(to="+491701234567", template_name="x", lang="de", components=[])
        self.assertTrue(cm.exception.retryable)

    @responses.activate
    def test_submit_template_posts_to_waba(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/222/message_templates",
            json={"id": "TPL_1", "status": "PENDING"},
            status=200,
        )
        resp = meta_client.submit_template(
            {"name": "hi", "language": "de", "category": "MARKETING", "components": []}
        )
        self.assertEqual(resp["id"], "TPL_1")
