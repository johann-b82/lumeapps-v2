frappe.ui.form.on("Sensor", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Poll Now"), () => {
			frappe.show_alert({ message: __("Polling…"), indicator: "blue" });
			frappe.call({
				method: "sensor_monitor.sensor_monitor.api.poll_now",
				args: { sensor: frm.doc.name },
				callback: (r) => {
					const m = r.message || {};
					if (m.success) {
						frappe.show_alert({
							message: __("OK — {0} °C / {1} %", [m.temperature, m.humidity]),
							indicator: "green",
						});
					} else {
						frappe.show_alert({
							message: __("Failed: {0}", [m.error_kind || "unknown"]),
							indicator: "red",
						});
					}
				},
			});
		}, __("Actions"));

		frm.add_custom_button(__("Open Dashboard"), () => {
			frappe.set_route("sensor-dashboard", { sensor: frm.doc.name });
		}, __("Actions"));

		frm.add_custom_button(__("Recent Readings"), () => {
			frappe.set_route("List", "Sensor Reading", { sensor: frm.doc.name });
		}, __("View"));

		frm.add_custom_button(__("Poll Log"), () => {
			frappe.set_route("List", "Sensor Poll Log", { sensor: frm.doc.name });
		}, __("View"));
	},
});
