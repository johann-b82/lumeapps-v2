// Redirect workspace home `/app/sensor-monitor` -> dashboard page.
(function () {
	function maybe_redirect() {
		const r = frappe.get_route ? frappe.get_route() : null;
		if (r && r[0] === "Workspaces" && r[1] === "Sensor Monitor") {
			frappe.set_route("sensor-dashboard");
		}
	}
	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on("change", maybe_redirect);
		// Also run once at boot in case we land directly
		$(document).ready(maybe_redirect);
	}
})();
