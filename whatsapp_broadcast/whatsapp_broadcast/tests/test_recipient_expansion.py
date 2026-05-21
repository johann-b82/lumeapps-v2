import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import expand_recipients


def _recipient(phone, name, tags=None, opted=True):
    if frappe.db.exists("WhatsApp Recipient", phone):
        frappe.delete_doc("WhatsApp Recipient", phone, force=True)
    return frappe.get_doc({
        "doctype": "WhatsApp Recipient",
        "recipient_name": name, "phone_number": phone,
        "opt_in_status": "opted_in" if opted else "opted_out",
        "tags": [{"tag": t} for t in (tags or [])],
    }).insert(ignore_permissions=True)


def _tag(name):
    if not frappe.db.exists("WhatsApp Tag", name):
        frappe.get_doc({"doctype": "WhatsApp Tag", "tag_name": name}).insert(ignore_permissions=True)


def _ensure_template():
    name = "expansion_tpl"
    if not frappe.db.exists("WhatsApp Template", name):
        frappe.get_doc({
            "doctype": "WhatsApp Template", "template_name": name,
            "language": "de", "category": "MARKETING",
            "header_type": "none", "body_text": "Hi", "meta_status": "approved",
        }).insert(ignore_permissions=True)
    return name


class TestRecipientExpansion(FrappeTestCase):
    def setUp(self):
        _tag("vip"); _tag("beta")
        _recipient("+491700000001", "A", ["vip"])
        _recipient("+491700000002", "B", ["vip", "beta"])
        _recipient("+491700000003", "C", ["beta"])
        _recipient("+491700000004", "D", ["vip"], opted=False)

    def test_by_tags_returns_opted_in_dedup(self):
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "p1",
            "template": _ensure_template(), "variable_values": "{}",
            "recipient_mode": "by_tags",
            "recipient_tags": [{"tag": "vip"}, {"tag": "beta"}],
        }).insert(ignore_permissions=True)
        targets, skipped = expand_recipients(post.name)
        phones = sorted(r.phone_number for r in targets)
        self.assertEqual(phones, ["+491700000001", "+491700000002", "+491700000003"])
        self.assertEqual(skipped, 1)

    def test_explicit_list_filters_opted_out(self):
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "p2",
            "template": _ensure_template(), "variable_values": "{}",
            "recipient_mode": "explicit_list",
            "explicit_recipients": [
                {"recipient": "+491700000001"},
                {"recipient": "+491700000004"},
            ],
        }).insert(ignore_permissions=True)
        targets, skipped = expand_recipients(post.name)
        self.assertEqual([r.phone_number for r in targets], ["+491700000001"])
        self.assertEqual(skipped, 1)
