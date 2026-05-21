import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import validate_for_send


def _tpl(name, body, meta_status="approved", header_type="none"):
    if frappe.db.exists("WhatsApp Template", name):
        return name
    frappe.get_doc({
        "doctype": "WhatsApp Template", "template_name": name,
        "language": "de", "category": "MARKETING",
        "header_type": header_type, "body_text": body,
        "meta_status": meta_status,
    }).insert(ignore_permissions=True)
    return name


class TestPostValidation(FrappeTestCase):
    def test_send_blocked_when_template_not_approved(self):
        tpl = _tpl("pending_tpl", "Hi {{1}}", meta_status="pending")
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "x", "template": tpl,
            "variable_values": '{"1":"A"}', "recipient_mode": "explicit_list",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            validate_for_send(post)

    def test_send_blocked_when_variables_missing(self):
        tpl = _tpl("vars_tpl", "Hi {{1}} {{2}}")
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "y", "template": tpl,
            "variable_values": '{"1":"A"}', "recipient_mode": "explicit_list",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            validate_for_send(post)

    def test_send_blocked_when_media_header_without_attachment(self):
        tpl = _tpl("img_tpl", "Hi", header_type="image")
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "z", "template": tpl,
            "variable_values": "{}", "recipient_mode": "explicit_list",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            validate_for_send(post)
