frappe.ui.form.on('WhatsApp Template', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Submit to Meta'), () => {
                frappe.call({
                    method: 'whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_template.whatsapp_template.submit_to_meta',
                    args: { name: frm.doc.name },
                    callback: () => { frappe.show_alert({message: 'Submitted', indicator: 'green'}); frm.reload_doc(); },
                });
            });
            frm.add_custom_button(__('Sync Status'), () => {
                frappe.call({
                    method: 'whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_template.whatsapp_template.sync_status',
                    args: { name: frm.doc.name },
                    callback: () => { frm.reload_doc(); },
                });
            });
        }
    },
});
