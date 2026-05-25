/* eslint-disable */
frappe.listview_settings["HVV Stop"] = {
    add_fields: ["lines_cache"],
    onload(list_view) {
        list_view.page.add_inner_button(__("Stationen synchronisieren"), () => {
            frappe.call({
                method: "hvv_departures.api.endpoints.sync_stations",
                freeze: true,
                freeze_message: __("Sync ..."),
                callback: (r) => {
                    const m = r.message || {};
                    frappe.show_alert({
                        message: `${m.synced || 0} im Radius gespeichert, ${m.deleted || 0} außerhalb gelöscht`,
                        indicator: "green",
                    });
                    list_view.refresh();
                },
            });
        });
    },
};
