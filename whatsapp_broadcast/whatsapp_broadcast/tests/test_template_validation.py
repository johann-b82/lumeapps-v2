import frappe
from frappe.tests.utils import FrappeTestCase


def _make(template_name="t1", body="Hello {{1}} and {{2}}", header_type="none", footer=None, buttons=None):
    return frappe.get_doc({
        "doctype": "WhatsApp Template",
        "template_name": template_name,
        "language": "de",
        "category": "MARKETING",
        "header_type": header_type,
        "body_text": body,
        "footer_text": footer or "",
        "buttons": buttons or [],
    })


class TestTemplateValidation(FrappeTestCase):
    def test_variable_count_computed_from_body(self):
        doc = _make(template_name="vc_tpl", body="Hi {{1}}, your order {{2}} ships {{3}}.")
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.variable_count, 3)
        doc.delete()

    def test_body_over_1024_chars_throws(self):
        doc = _make(template_name="too_long", body="x" * 1025)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_footer_over_60_chars_throws(self):
        doc = _make(template_name="bad_footer", footer="y" * 61)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_invalid_template_name_throws(self):
        doc = _make(template_name="Bad-Name")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_new_template_defaults_to_local_status(self):
        doc = _make(template_name="status_default")
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.meta_status, "local")
        doc.delete()


import responses
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_template.whatsapp_template import (
    submit_to_meta, sync_status,
)


class TestTemplateActions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        s = frappe.get_single("WhatsApp Settings")
        s.phone_number_id = "111"; s.business_account_id = "222"
        s.access_token = "TOKEN"; s.webhook_verify_token = "VT"; s.app_secret = "SECRET"
        s.save(ignore_permissions=True); frappe.db.commit()

    @responses.activate
    def test_submit_to_meta_sets_pending_and_id(self):
        doc = _make(template_name="action_submit")
        doc.insert(ignore_permissions=True)
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/222/message_templates",
            json={"id": "TPL_X", "status": "PENDING"}, status=200,
        )
        submit_to_meta(doc.name)
        doc.reload()
        self.assertEqual(doc.meta_status, "pending")
        self.assertEqual(doc.meta_template_id, "TPL_X")

    @responses.activate
    def test_sync_status_updates_approved(self):
        doc = _make(template_name="action_sync")
        doc.insert(ignore_permissions=True)
        doc.db_set("meta_template_id", "TPL_Y")
        responses.add(
            responses.GET,
            "https://graph.facebook.com/v20.0/222/message_templates",
            json={"data": [{"name": "action_sync", "language": "de", "status": "APPROVED", "id": "TPL_Y"}]},
            status=200,
        )
        sync_status(doc.name)
        doc.reload()
        self.assertEqual(doc.meta_status, "approved")
