// Walking icon (inline SVG) + helper
const WALK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><circle cx="13" cy="4" r="2"/><path d="M9 20l3-6 2 2 3 5"/><path d="M6 8l3.5-1L13 10l-2.5 2.5L9 17"/></svg>`;
const CHEV_DOWN = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="m6 9 6 6 6-6"/></svg>`;
const CHEV_UP = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><path d="m18 15-6-6-6 6"/></svg>`;
function walk_min(distance_m) {
    // 80 m/min ~ 4.8 km/h typical pedestrian
    return Math.max(1, Math.round(distance_m / 80));
}

// HVV-style line badge
const HVV_COLORS = {
    "U1": "#005fae", "U2": "#dc0021", "U3": "#ffd006", "U4": "#0098a1", "U5": "#88c540",
    "S1": "#3ea535", "S2": "#cc1c20", "S3": "#5b1f7e", "S4": "#c8b400", "S5": "#0080c8",
    "S11": "#3ea535", "S21": "#cc1c20", "S31": "#5b1f7e",
    "A1": "#a3195b", "A2": "#a3195b", "A3": "#a3195b",
};
const HVV_TYPE_COLORS = {
    "U": "#003d7d", "S": "#3ea535", "A": "#a3195b", "R": "#878432",
    "BUS": "#e2001a", "STADTBUS": "#e2001a", "METROBUS": "#e2001a",
    "XPRESSBUS": "#231f20", "SCHNELLBUS": "#a40e26", "NACHTBUS": "#231f20",
    "REGIONALBUS": "#005fae", "AKN": "#a3195b", "FAEHRE": "#0080c8",
    "ZUG": "#666", "RB": "#878432", "RE": "#878432",
};
function line_color(line) {
    const name = (line && line.name) || "";
    if (HVV_COLORS[name]) return HVV_COLORS[name];
    const t = ((line && line.type && line.type.simpleType) || "").toUpperCase();
    if (HVV_TYPE_COLORS[t]) return HVV_TYPE_COLORS[t];
    // Try prefix (U1 -> U, S3 -> S)
    const m = name.match(/^([A-Z]+)\d/);
    if (m && HVV_TYPE_COLORS[m[1]]) return HVV_TYPE_COLORS[m[1]];
    // Fallback: infer from name (numeric -> BUS red)
    const inferred = infer_type_from_name(name);
    if (HVV_TYPE_COLORS[inferred]) return HVV_TYPE_COLORS[inferred];
    return "#555";
}
function infer_type_from_name(name) {
    if (!name) return "";
    if (/^U\d/.test(name)) return "U";
    if (/^S\d/.test(name)) return "S";
    if (/^A\d/.test(name)) return "A";
    if (/^(RE|RB|R)\d/.test(name)) return "R";
    // numeric, M-prefix, X-prefix, N-prefix → bus
    if (/^(\d|M\d|X\d|N\d)/.test(name)) return "BUS";
    return "";
}
function line_badge(line) {
    const name = (line && line.name) || "?";
    let t = ((line && line.type && line.type.simpleType) || "").toUpperCase();
    if (!t) t = infer_type_from_name(name);
    const bg = line_color(line);
    const fg = (bg === "#ffd006") ? "#000" : "#fff";
    // Bus types use hexagon shape, rail/ferry use rounded rect
    const is_bus = /BUS$/.test(t) || t === "FAEHRE" || t === "BUS";
    const shape = is_bus
        ? "clip-path:polygon(10% 0,90% 0,100% 50%,90% 100%,10% 100%,0 50%);"
        : "border-radius:4px;";
    return `<span style="display:inline-block;padding:2px 10px;text-align:center;font-weight:700;font-size:12px;line-height:16px;background:${bg};color:${fg};${shape}">${frappe.utils.escape_html(name)}</span>`;
}

frappe.pages["hvv-map"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "HVV Karte",
        single_column: true,
    });

    page.add_inner_button("Stationen synchronisieren", () => {
        frappe.call({
            method: "hvv_departures.api.endpoints.sync_stations",
            freeze: true,
            freeze_message: "Synchronisiere Stationen ...",
            callback: (r) => {
                frappe.show_alert({ message: `${r.message.synced} Stationen aktualisiert`, indicator: "green" });
                load_nearby();
            },
        });
    });

    page.add_inner_button("Aktualisieren", () => load_nearby());

    // Searchable stop selector (uses HVV Stop Link control = autocomplete with search)
    const stop_field = page.add_field({
        label: "Stop suchen",
        fieldtype: "Link",
        fieldname: "stop_search",
        options: "HVV Stop",
        change: () => {
            const v = stop_field.get_value();
            if (v) focus_stop(v);
        },
    });

    const $container = $(`
        <div class="hvv-map-wrap" style="padding: 0 15px;">
          <button class="btn btn-xs btn-default hvv-map-toggle" style="margin-bottom:8px;">
            <span class="hvv-map-label">Karte anzeigen</span> <span class="hvv-map-arrow">${CHEV_DOWN}</span>
          </button>
          <div id="hvv-map" style="height: 480px; border-radius: 8px; margin-bottom: 16px; display:none;"></div>
          <div id="hvv-list"></div>
        </div>
    `).appendTo(page.body);

    $container.find(".hvv-map-toggle").on("click", () => {
        const $m = $("#hvv-map");
        const $arrow = $container.find(".hvv-map-arrow");
        const $label = $container.find(".hvv-map-label");
        if ($m.is(":visible")) {
            $m.slideUp(() => { $arrow.html(CHEV_DOWN); $label.text("Karte anzeigen"); });
        } else {
            $m.slideDown(() => { if (map) map.invalidateSize(); });
            $arrow.html(CHEV_UP);
            $label.text("Karte verbergen");
        }
    });

    function focus_stop(stop_id) {
        frappe.db.get_doc("HVV Stop", stop_id).then((doc) => {
            if (!doc || doc.lat == null || doc.lon == null) return;
            if (map) map.setView([doc.lat, doc.lon], 17);
            const $row = $(`#hvv-list .hvv-row[data-stop-id="${CSS.escape(stop_id)}"]`);
            if ($row.length) {
                $row[0].scrollIntoView({ behavior: "smooth", block: "center" });
                if (!$row.find(".hvv-departures").is(":visible")) $row.find(".hvv-toggle").click();
            } else {
                // Stop outside radius - render single-row + open departures
                render([{ stop_id: doc.stop_id, stop_name: doc.stop_name, lat: doc.lat, lon: doc.lon, type: doc.type, distance_m: 0 }]);
                $(`#hvv-list .hvv-row[data-stop-id="${CSS.escape(stop_id)}"] .hvv-toggle`).click();
            }
        });
    }

    const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

    function load_css(href) {
        if (document.querySelector(`link[href="${href}"]`)) return Promise.resolve();
        return new Promise((res) => {
            const l = document.createElement("link");
            l.rel = "stylesheet";
            l.href = href;
            l.onload = res;
            document.head.appendChild(l);
        });
    }
    function load_js(src) {
        if (document.querySelector(`script[src="${src}"]`)) return Promise.resolve();
        return new Promise((res) => {
            const s = document.createElement("script");
            s.src = src;
            s.onload = res;
            document.head.appendChild(s);
        });
    }

    let map;
    let layer_group;

    async function init() {
        await load_css(LEAFLET_CSS);
        await load_js(LEAFLET_JS);
        const center = await frappe.call({ method: "hvv_departures.api.endpoints.get_center" });
        const c = center.message;
        map = L.map("hvv-map").setView([c.lat, c.lon], 15);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap",
        }).addTo(map);
        L.circle([c.lat, c.lon], { radius: c.radius_m, color: "#0d6efd", fillOpacity: 0.05 }).addTo(map);
        L.marker([c.lat, c.lon]).addTo(map).bindPopup("Brandstücken 16");
        layer_group = L.layerGroup().addTo(map);
        load_nearby();
        // Open requested stop from query (?stop=<id>) or route state
        const qs = new URLSearchParams(window.location.search);
        const stop_param = qs.get("stop") || (frappe.route_options && frappe.route_options.stop);
        if (frappe.route_options) frappe.route_options = null;
        if (stop_param) {
            setTimeout(() => focus_stop(stop_param), 400);
        }
    }

    function load_nearby() {
        frappe.call({
            method: "hvv_departures.api.endpoints.nearby_with_lines",
            callback: (r) => render(r.message || []),
            error: (err) => { console.error("HVV nearby_with_lines error", err); frappe.show_alert({message: "Fehler beim Laden der Stationen", indicator: "red"}); },
        });
    }

    function parse_lines_cache(lc) {
        // "21 → Teufelsbrück; M3 → Schenefelder Platz" → unique line names
        if (!lc) return [];
        const seen = new Set();
        lc.split(";").forEach((part) => {
            const name = part.split("→")[0].trim();
            if (name) seen.add(name);
        });
        return Array.from(seen);
    }

    function render(stops) {
        if (layer_group) layer_group.clearLayers();
        const $list = $("#hvv-list").empty();
        if (!stops.length) {
            $list.html(`<div class="text-muted">Keine Stationen im Radius. Klicke "Stationen synchronisieren".</div>`);
            return;
        }
        stops.forEach((s) => {
            const m = L.marker([s.lat, s.lon]).addTo(layer_group);
            m.bindPopup(`<b>${frappe.utils.escape_html(s.stop_name)}</b><br>${Math.round(s.distance_m)} m · ${WALK_SVG} ${walk_min(s.distance_m)} min`);
            const lines = parse_lines_cache(s.lines_cache);
            const badges_html = lines.map((name) => line_badge({ name })).join(" ");
            const $row = $(`
                <div class="hvv-row" data-stop-id="${frappe.utils.escape_html(s.stop_id)}" style="border:1px solid var(--border-color); border-radius:6px; padding:10px; margin-bottom:8px;">
                  <div class="hvv-row-header" style="display:flex;justify-content:space-between;align-items:center;gap:8px;cursor:pointer;">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                      <span class="hvv-badges">${badges_html}</span>
                      <b>${frappe.utils.escape_html(s.stop_name)}</b>
                      <span class="text-muted">${Math.round(s.distance_m)} m · ${WALK_SVG} ${walk_min(s.distance_m)} min</span>
                    </div>
                    <button class="btn btn-xs btn-default hvv-toggle"><span class="hvv-toggle-label">Abfahrten</span> <span class="hvv-toggle-arrow">${CHEV_UP}</span></button>
                  </div>
                  <div class="hvv-departures" style="margin-top:8px;display:none;"></div>
                </div>
            `).appendTo($list);
            $row.find(".hvv-toggle").on("click", () => toggle_departures(s.stop_id, $row));
            // Whole header is clickable too
            $row.find(".hvv-row-header").on("click", (e) => {
                if ($(e.target).closest(".hvv-toggle").length) return;
                toggle_departures(s.stop_id, $row);
            });
            // Auto-expand departures by default
            toggle_departures(s.stop_id, $row);
        });
    }

    function toggle_departures(station_id, $row) {
        const $box = $row.find(".hvv-departures");
        const $arrow = $row.find(".hvv-toggle-arrow");
        if ($box.is(":visible")) {
            $box.slideUp(() => $arrow.html(CHEV_DOWN));
            return;
        }
        $arrow.html(CHEV_UP);
        $box.html(`<div class="text-muted">Lade ...</div>`).slideDown();
        frappe.call({
            method: "hvv_departures.api.endpoints.departures",
            args: { station_id, max_results: 15 },
            callback: (r) => {
                const deps = (r.message && r.message.departures) || [];
                if (!deps.length) {
                    $box.html(`<div class="text-muted">Keine Abfahrten.</div>`);
                    return;
                }
                // Update header badges from actual lines in this response
                const uniq_lines = {};
                deps.forEach((d) => {
                    const n = (d.line && d.line.name) || "";
                    if (n && !uniq_lines[n]) uniq_lines[n] = d.line;
                });
                const new_badges = Object.values(uniq_lines).map(line_badge).join(" ");
                if (new_badges) $row.find(".hvv-badges").html(new_badges);

                // Group by direction
                const base = new Date();
                const groups = {}; // direction -> entries
                deps.forEach((d) => {
                    const dir = (d.line && d.line.direction) || "—";
                    const key = `${(d.line && d.line.name) || ""}|${dir}`;
                    if (!groups[key]) groups[key] = { name: (d.line && d.line.name) || "", direction: dir, line: d.line, items: [] };
                    const offset_min = typeof d.timeOffset === "number" ? d.timeOffset : 0;
                    const dt = new Date(base.getTime() + offset_min * 60000);
                    const t = dt.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
                    const delay = d.delay ? ` <span class="text-danger">+${Math.round(d.delay / 60)}m</span>` : "";
                    groups[key].items.push({ t, delay });
                });

                const cols = Object.values(groups).map((g) => {
                    const rows = g.items.map((it) => `<div style="white-space:nowrap;">${it.t}${it.delay}</div>`).join("");
                    return `
                        <div class="hvv-dir-col" style="flex:1 1 180px;min-width:180px;border:1px solid var(--border-color);border-radius:6px;padding:8px;">
                          <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
                            ${line_badge(g.line || { name: g.name })}
                            <span style="font-weight:600;">→ ${frappe.utils.escape_html(g.direction)}</span>
                          </div>
                          <div style="font-size:13px;display:flex;flex-direction:column;gap:2px;">${rows}</div>
                        </div>
                    `;
                }).join("");
                $box.html(`<div style="display:flex;flex-wrap:wrap;gap:8px;">${cols}</div>`);
            },
        });
    }

    init();
};
