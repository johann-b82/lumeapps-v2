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
