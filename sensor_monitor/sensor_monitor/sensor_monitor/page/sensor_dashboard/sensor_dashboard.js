// v3-area
frappe.pages["sensor-dashboard"].on_page_load = (wrapper) => {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sensor Dashboard"),
		single_column: true,
	});

	const state = {
		window: "24h",
		settings: {},
		charts: {},
		timer: null,
	};

	const $window = page.add_field({
		fieldname: "window",
		label: __("Window"),
		fieldtype: "Select",
		options: ["1h", "6h", "24h", "7d", "30d"].join("\n"),
		default: "24h",
		change: () => { state.window = $window.get_value(); refresh(); },
	});

	page.set_primary_action(__("Refresh"), () => refresh(), "refresh");

	const $body = $(`<div class="sensor-dashboard p-3"></div>`).appendTo(page.body);

	$(`<style>
		.sensor-dashboard .sensor-block { margin-bottom:24px; padding:16px; border:1px solid var(--border-color); border-radius:12px; background:var(--card-bg); }
		.sensor-dashboard .sensor-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; cursor:pointer; }
		.sensor-dashboard .sensor-name { font-weight:600; font-size:16px; }
		.sensor-dashboard .kpi-row { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
		.sensor-dashboard .kpi { flex:1; min-width:160px; padding:12px; border:1px solid var(--border-color); border-radius:10px; }
		.sensor-dashboard .kpi .lbl { font-size:11px; color:var(--text-muted); text-transform:uppercase; letter-spacing:.4px; }
		.sensor-dashboard .kpi .val { font-size:24px; font-weight:600; margin-top:2px; }
		.sensor-dashboard .kpi .sub { font-size:11px; color:var(--text-muted); margin-top:4px; }
		.sensor-dashboard .pill { padding:2px 8px; border-radius:9999px; font-size:11px; font-weight:600; }
		.sensor-dashboard .pill.ok { background:var(--control-bg); color:var(--text-muted); }
		.sensor-dashboard .pill.bad { background:#fee2e2; color:#991b1b; }
		.sensor-dashboard .charts-row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
		.sensor-dashboard .chart-host { min-height:200px; }
		.sensor-dashboard .frappe-chart .y-markers .line-horizontal.dashed { stroke:#ef4444 !important; }
		@media (max-width: 900px) { .sensor-dashboard .charts-row { grid-template-columns:1fr; } }
	</style>`).appendTo("head");

	function fmt(v, unit) {
		return v === null || v === undefined ? "—" : `${(+v).toFixed(2)} ${unit}`;
	}

	function fmtTs(v) {
		if (!v) return "";
		const d = new Date(v.replace(" ", "T"));
		if (isNaN(d.getTime())) return v;
		const p = n => String(n).padStart(2, "0");
		return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
	}

	function markBreaches($el, values, min, max) {
		const draw = () => {
			const svg = $el.find("svg.frappe-chart").get(0);
			if (!svg) return false;
			const path = svg.querySelector("path.line-graph-path");
			if (!path) return false;
			const parent = path.parentElement;
			parent.querySelectorAll(".breach-dot").forEach(e => e.remove());
			const d = path.getAttribute("d") || "";
			const pts = [];
			const re = /[ML]\s*([-\d.]+)[ ,]([-\d.]+)/g;
			let m;
			while ((m = re.exec(d))) pts.push({ x: +m[1], y: +m[2] });
			if (pts.length !== values.length) return false;
			const ns = "http://www.w3.org/2000/svg";
			parent.querySelectorAll(".breach-line").forEach(e => e.remove());
			const isBreach = i => {
				const v = values[i];
				if (v == null) return false;
				const low = min != null && min !== 0 && v < min;
				const high = max != null && max !== 0 && v > max;
				return low || high;
			};
			let run = [];
			const flush = () => {
				if (run.length < 2) { run = []; return; }
				const pl = document.createElementNS(ns, "polyline");
				pl.setAttribute("points", run.map(i => `${pts[i].x},${pts[i].y}`).join(" "));
				pl.setAttribute("fill", "none");
				pl.setAttribute("stroke", "#ef4444");
				pl.setAttribute("stroke-width", "2");
				pl.setAttribute("class", "breach-line");
				parent.appendChild(pl);
				run = [];
			};
			values.forEach((_, i) => {
				if (isBreach(i)) run.push(i);
				else flush();
			});
			flush();
			return true;
		};
		setTimeout(draw, 1200);
		setTimeout(draw, 2000);
	}

	function yMarkers(min, max, unit) {
		const out = [];
		if (min !== null && min !== undefined && min !== 0)
			out.push({ label: `${__("Min")} ${(+min).toFixed(1)}${unit}`, value: +min, type: "dashed", options: { labelPos: "left" } });
		if (max !== null && max !== undefined && max !== 0)
			out.push({ label: `${__("Max")} ${(+max).toFixed(1)}${unit}`, value: +max, type: "dashed", options: { labelPos: "left" } });
		return out;
	}

	async function refresh() {
		const [sensors, settings] = await Promise.all([
			frappe.call({ method: "sensor_monitor.sensor_monitor.api.list_sensors" }).then(r => r.message || []),
			frappe.call({ method: "sensor_monitor.sensor_monitor.api.get_settings" }).then(r => r.message || {}),
		]);
		state.settings = settings;

		const valid = new Set(sensors.map(s => s.name));
		$body.children("[data-sensor]").each(function () {
			if (!valid.has($(this).attr("data-sensor"))) $(this).remove();
		});

		for (const s of sensors) {
			let $block = $body.find(`[data-sensor="${$.escapeSelector(s.name)}"]`);
			if (!$block.length) {
				$block = $(`
					<div class="sensor-block" data-sensor="${frappe.utils.escape_html(s.name)}">
						<div class="sensor-head">
							<div class="sensor-name">${frappe.utils.escape_html(s.sensor_name || s.name)}</div>
							<div class="health-pill">—</div>
						</div>
						<div class="kpi-row">
							<div class="kpi"><div class="lbl">${__("Temperature")}</div><div class="val" data-k="t">—</div></div>
							<div class="kpi"><div class="lbl">${__("Humidity")}</div><div class="val" data-k="h">—</div></div>
							<div class="kpi"><div class="lbl">${__("Host")}</div><div class="val">${frappe.utils.escape_html(s.host || "—")}:${s.port || 161}</div><div class="sub">${s.enabled ? __("Enabled") : __("Disabled")}</div></div>
						</div>
						<div class="charts-row">
							<div class="chart-host" data-chart="t"></div>
							<div class="chart-host" data-chart="h"></div>
						</div>
					</div>
				`).appendTo($body);
				$block.find(".sensor-head").on("click", () => frappe.set_route("Form", "Sensor", s.name));
			}

			const [readings, latest, health] = await Promise.all([
				frappe.call({ method: "sensor_monitor.sensor_monitor.api.get_readings", args: { sensor: s.name, window: state.window } }).then(r => r.message),
				frappe.call({ method: "sensor_monitor.sensor_monitor.api.get_latest", args: { sensor: s.name } }).then(r => r.message),
				frappe.call({ method: "sensor_monitor.sensor_monitor.api.health", args: { sensor: s.name } }).then(r => r.message),
			]);

			const tNow = latest && latest.temperature;
			const hNow = latest && latest.humidity;
			$block.find('[data-k="t"]').text(fmt(tNow, "°C"));
			$block.find('[data-k="h"]').text(fmt(hNow, "%"));
			const ok = health && health.last_success;
			$block.find(".health-pill")
				.removeClass("pill ok bad")
				.addClass("pill " + (ok ? "ok" : "bad"))
				.text(ok ? `${__("Last updated")}: ${fmtTs(health.last_success)}` : (health.last_error || __("Offline")));

			const labels = (readings.rows || []).map(r => r.recorded_at);
			const temps  = (readings.rows || []).map(r => r.temperature);
			const hums   = (readings.rows || []).map(r => r.humidity);

			const $t = $block.find('[data-chart="t"]').empty();
			const $h = $block.find('[data-chart="h"]').empty();

			if (!labels.length) {
				$t.html(`<div class="text-muted small">${__("No readings in this window.")}</div>`);
				$h.empty();
				continue;
			}

			state.charts[s.name + ":t"] = new frappe.Chart($t.get(0), {
				title: __("Temperature"),
				data: { labels, datasets: [{ name: "°C", values: temps, chartType: "line" }],
					yMarkers: yMarkers(settings.global_temperature_min, settings.global_temperature_max, " °C") },
				type: "line",
				height: 220,
				lineOptions: { regionFill: 1, hideDots: 1 },
				axisOptions: { xIsSeries: true, xAxisMode: "tick" },
				colors: ["#f59e0b"],
			});
			state.charts[s.name + ":h"] = new frappe.Chart($h.get(0), {
				title: __("Humidity"),
				data: { labels, datasets: [{ name: "%", values: hums, chartType: "line" }],
					yMarkers: yMarkers(settings.global_humidity_min, settings.global_humidity_max, " %") },
				type: "line",
				height: 220,
				lineOptions: { regionFill: 1, hideDots: 1 },
				axisOptions: { xIsSeries: true, xAxisMode: "tick" },
				colors: ["#0ea5e9"],
			});
			markBreaches($t, temps, settings.global_temperature_min, settings.global_temperature_max);
			markBreaches($h, hums, settings.global_humidity_min, settings.global_humidity_max);
		}

		if (!sensors.length) {
			$body.empty().append(`<div class="text-muted p-4">${__("No sensors configured.")} <a href="/app/sensor/new?enabled=1">${__("Add one")}</a>.</div>`);
		}
	}

	refresh();
	state.timer = setInterval(refresh, 30000);
};
