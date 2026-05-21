frappe.ui.form.on('WhatsApp Post', {
    refresh(frm) {
        _render_preview(frm);
        _render_count(frm);
        if (!frm.is_new() && ['draft', 'failed'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Send'), () => _confirm_send(frm), __('Actions'));
        }
        if (frm.doc.status === 'sending' || frm.doc.status === 'queued') {
            _subscribe_progress(frm);
        }
    },
    template: _render_preview,
    variable_values: _render_preview,
    recipient_mode: _render_count,
    recipient_tags_add: _render_count,
    recipient_tags_remove: _render_count,
    explicit_recipients_add: _render_count,
    explicit_recipients_remove: _render_count,
});

function _format(text) {
    if (!text) return '';
    return frappe.utils.escape_html(text)
        .replace(/\*([^*]+)\*/g, '<b>$1</b>')
        .replace(/_([^_]+)_/g, '<i>$1</i>')
        .replace(/~([^~]+)~/g, '<s>$1</s>')
        .replace(/```([\s\S]+?)```/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

function _render_preview(frm) {
    if (!frm.doc.template || frm.is_new()) return;
    frappe.call({
        method: 'whatsapp_broadcast.api.post_helpers.preview',
        args: { post_name: frm.doc.name },
        callback: (r) => {
            const p = r.message || {};
            const html = `
                <div style="max-width:340px;background:#dcf8c6;padding:8px 12px;border-radius:8px;font-family:system-ui;">
                  ${p.header_content ? `<div style="font-weight:600;margin-bottom:4px;">${frappe.utils.escape_html(p.header_content)}</div>` : ''}
                  <div>${_format(p.body)}</div>
                  ${p.footer ? `<div style="color:#888;font-size:12px;margin-top:4px;">${frappe.utils.escape_html(p.footer)}</div>` : ''}
                  ${(p.buttons || []).map(b => `<div style="margin-top:6px;color:#1a73e8;">${frappe.utils.escape_html(b.text)}</div>`).join('')}
                </div>`;
            frm.dashboard.clear_headline();
            frm.dashboard.add_section(html, __('Preview'));
        },
    });
}

function _render_count(frm) {
    if (frm.is_new()) return;
    frappe.call({
        method: 'whatsapp_broadcast.api.post_helpers.recipient_count',
        args: { post_name: frm.doc.name },
        callback: (r) => {
            const m = r.message || {};
            frm.dashboard.set_headline_alert(
                `Recipients: <b>${m.total}</b> &nbsp; Skipped (opt-out): <b>${m.skipped_opt_out}</b>`
            );
        },
    });
}

function _confirm_send(frm) {
    frappe.call({
        method: 'whatsapp_broadcast.api.post_helpers.recipient_count',
        args: { post_name: frm.doc.name },
        callback: (r) => {
            const m = r.message || {};
            frappe.confirm(
                __(`Send to ${m.total} recipients via template "${frm.doc.template}"?`),
                () => {
                    frappe.call({
                        method: 'whatsapp_broadcast.tasks.sender.trigger_send',
                        args: { post_name: frm.doc.name },
                        callback: () => { frappe.show_alert({message: 'Queued', indicator: 'green'}); frm.reload_doc(); },
                    });
                }
            );
        },
    });
}

function _subscribe_progress(frm) {
    frappe.realtime.on('whatsapp_post_progress', (data) => {
        if (data.post === frm.doc.name) {
            frm.reload_doc();
        }
    });
}
