import responses
import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.tasks import sender


def _settings():
    s = frappe.get_single("WhatsApp Settings")
    s.phone_number_id = "111"
    s.business_account_id = "222"
    s.access_token = "TOKEN"
    s.webhook_verify_token = "VT"
    s.app_secret = "SECRET"
    s.rate_limit_per_second = 1000
    s.max_retries_5xx = 1
    s.save(ignore_permissions=True)
    frappe.db.commit()


def _seed():
    if not frappe.db.exists("WhatsApp Tag", "send"):
        frappe.get_doc({"doctype": "WhatsApp Tag", "tag_name": "send"}).insert(ignore_permissions=True)
    for phone, name in [("+491701111101", "S1"), ("+491701111102", "S2")]:
        if frappe.db.exists("WhatsApp Recipient", phone):
            frappe.delete_doc("WhatsApp Recipient", phone, force=True)
        frappe.get_doc({
            "doctype": "WhatsApp Recipient",
            "recipient_name": name, "phone_number": phone, "opt_in_status": "opted_in",
            "tags": [{"tag": "send"}],
        }).insert(ignore_permissions=True)
    if not frappe.db.exists("WhatsApp Template", "send_tpl"):
        frappe.get_doc({
            "doctype": "WhatsApp Template", "template_name": "send_tpl",
            "language": "de", "category": "MARKETING",
            "header_type": "none", "body_text": "Hi {{1}}", "meta_status": "approved",
        }).insert(ignore_permissions=True)


class TestSendIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _settings()
        _seed()

    @responses.activate
    def test_full_send_creates_logs_and_updates_counters(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.S1"}]}, status=200,
        )
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.S2"}]}, status=200,
        )
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "send_t1", "template": "send_tpl",
            "variable_values": '{"1":"Hans"}',
            "recipient_mode": "by_tags", "recipient_tags": [{"tag": "send"}],
        }).insert(ignore_permissions=True)
        sender.send_post(post.name, _inline=True)
        post.reload()
        self.assertEqual(post.status, "completed")
        self.assertEqual(post.total_recipients, 2)
        self.assertEqual(post.sent_count, 2)
        self.assertEqual(post.failed_count, 0)
        logs = frappe.get_all(
            "WhatsApp Message Log", filters={"post": post.name},
            fields=["meta_message_id", "status"],
        )
        ids = sorted(l.meta_message_id for l in logs)
        self.assertEqual(ids, ["wamid.S1", "wamid.S2"])
        self.assertTrue(all(l.status == "sent" for l in logs))

    @responses.activate
    def test_4xx_marks_failed_no_retry(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 132000, "message": "Bad"}}, status=400,
        )
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.OK"}]}, status=200,
        )
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "send_t2", "template": "send_tpl",
            "variable_values": '{"1":"Hans"}',
            "recipient_mode": "by_tags", "recipient_tags": [{"tag": "send"}],
        }).insert(ignore_permissions=True)
        sender.send_post(post.name, _inline=True)
        post.reload()
        self.assertEqual(post.sent_count + post.failed_count, 2)
        self.assertEqual(post.failed_count, 1)
        self.assertEqual(post.status, "completed")
