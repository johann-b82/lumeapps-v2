/* eslint-disable */
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

const WALK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;"><circle cx="13" cy="4" r="2"/><path d="M9 20l3-6 2 2 3 5"/><path d="M6 8l3.5-1L13 10l-2.5 2.5L9 17"/></svg>`;
function walk_min(distance_m) { return Math.max(1, Math.round(distance_m / 80)); }

function load_css(href) {
    if (document.querySelector(`link[href="${href}"]`)) return Promise.resolve();
    return new Promise((res) => { const l = document.createElement("link"); l.rel = "stylesheet"; l.href = href; l.onload = res; document.head.appendChild(l); });
}
function load_js(src) {
    if (document.querySelector(`script[src="${src}"]`)) return Promise.resolve();
    return new Promise((res) => { const s = document.createElement("script"); s.src = src; s.onload = res; document.head.appendChild(s); });
}

function run_test_connection() {
    frappe.call({
        method: "hvv_departures.api.endpoints.test_connection",
        freeze: true,
        freeze_message: __("Teste Geofox API ..."),
        callback: (r) => {
            const m = r.message || {};
            if (m.ok) {
                const details = [
                    m.version ? `Version: ${m.version}` : null,
                    m.build ? `Build: ${m.build}` : null,
                    m.begin_of_service ? `Service ab: ${m.begin_of_service}` : null,
                    m.end_of_service ? `Service bis: ${m.end_of_service}` : null,
                ].filter(Boolean).join("<br>");
                frappe.msgprint({ title: __("Verbindung OK"), indicator: "green", message: `<b>${__("Geofox API erreichbar.")}</b><br><br>${details}` });
            } else {
                frappe.msgprint({ title: __("Verbindung fehlgeschlagen"), indicator: "red",
                    message: `<b>${frappe.utils.escape_html(m.error || "Unbekannter Fehler")}</b>` +
                        (m.return_code ? `<br><small>Return Code: ${frappe.utils.escape_html(m.return_code)}</small>` : "") });
            }
        },
    });
}

const _state = { map: null, center_marker: null, radius_circle: null, station_layer: null, station_markers: {}, selected_stop: null, search_timer: null };

async function ensure_map_ready(frm) {
    if (_state.map) return;
    const wrapper = frm.get_field("location_search_html").$wrapper;
    if (!wrapper || !wrapper.length) return;
    wrapper.empty().html(`
        <div class="hvv-locsearch">
          <div class="hvv-locsearch-map" style="height:380px;border-radius:8px;border:1px solid var(--border-color);"></div>
          <div class="hvv-locsearch-status text-muted" style="margin-top:6px;font-size:12px;"></div>
          <div class="hvv-station-cards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:10px;"></div>
          <div class="hvv-locsearch-actions" style="margin-top:12px;display:none;gap:8px;">
            <button class="btn btn-primary hvv-take-on-map" disabled>${__("Auf Karte anzeigen")}</button>
            <button class="btn btn-default hvv-save-as-default" disabled>${__("Als Default Stop speichern")}</button>
            <span class="hvv-selected-info text-muted" style="align-self:center;"></span>
          </div>
        </div>
    `);

    await load_css(LEAFLET_CSS);
    await load_js(LEAFLET_JS);

    const map_el = wrapper.find(".hvv-locsearch-map")[0];
    const init_lat = frm.doc.center_lat || 53.5703;
    const init_lon = frm.doc.center_lon || 9.8585;
    _state.map = L.map(map_el).setView([init_lat, init_lon], 15);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "&copy; OpenStreetMap" }).addTo(_state.map);
    _state.station_layer = L.layerGroup().addTo(_state.map);
    setTimeout(() => _state.map.invalidateSize(), 250);

    wrapper.off("click", ".hvv-take-on-map").on("click", ".hvv-take-on-map", (e) => {
        e.preventDefault();
        if (!_state.selected_stop) return;
        frappe.set_route("hvv-map", { stop: _state.selected_stop.stop_id });
    });
    wrapper.off("click", ".hvv-save-as-default").on("click", ".hvv-save-as-default", (e) => {
        e.preventDefault();
        if (!_state.selected_stop) return;
        frm.set_value("default_stop", _state.selected_stop.stop_id);
        frm.save();
    });
}

function set_status(frm, msg) {
    frm.get_field("location_search_html").$wrapper.find(".hvv-locsearch-status").text(msg || "");
}

function set_center(lat, lon, radius) {
    if (_state.center_marker) _state.center_marker.remove();
    if (_state.radius_circle) _state.radius_circle.remove();
    _state.center_marker = L.marker([lat, lon]).addTo(_state.map).bindPopup(__("Zentrum"));
    _state.radius_circle = L.circle([lat, lon], { radius: radius, color: "#0d6efd", fillOpacity: 0.05 }).addTo(_state.map);
    _state.map.setView([lat, lon], 15);
}

function select_stop(frm, s, $card) {
    _state.selected_stop = s;
    const wrapper = frm.get_field("location_search_html").$wrapper;
    wrapper.find(".hvv-card").css({ "border-color": "var(--border-color)", "background": "transparent" });
    if ($card && $card.length) $card.css({ "border-color": "var(--primary)", "background": "var(--bg-light-gray)" });
    const m = _state.station_markers[s.stop_id];
    if (m) { m.openPopup(); _state.map.panTo(m.getLatLng()); }
    wrapper.find(".hvv-selected-info").text(`${__("Ausgewählt")}: ${s.stop_name}`);
    wrapper.find(".hvv-take-on-map, .hvv-save-as-default").prop("disabled", false);
}

function render_cards_and_markers(frm, stops) {
    const wrapper = frm.get_field("location_search_html").$wrapper;
    const $cards = wrapper.find(".hvv-station-cards").empty();
    _state.station_layer.clearLayers();
    _state.station_markers = {};
    _state.selected_stop = null;
    wrapper.find(".hvv-take-on-map, .hvv-save-as-default").prop("disabled", true);
    wrapper.find(".hvv-selected-info").text("");

    if (!stops.length) {
        $cards.html(`<div class="text-muted">${__("Keine Haltestellen im Umkreis.")}</div>`);
        wrapper.find(".hvv-locsearch-actions").hide();
        return;
    }

    const bounds = [];
    stops.forEach((s) => {
        const m = L.marker([s.lat, s.lon]).addTo(_state.station_layer);
        m.bindPopup(`<b>${frappe.utils.escape_html(s.stop_name)}</b><br>${Math.round(s.distance_m)} m · ${WALK_SVG} ${walk_min(s.distance_m)} min`);
        m.on("click", () => {
            const $card = wrapper.find(`.hvv-card[data-stop-id="${CSS.escape(s.stop_id)}"]`);
            select_stop(frm, s, $card);
        });
        _state.station_markers[s.stop_id] = m;
        bounds.push([s.lat, s.lon]);

        const $card = $(`
            <div class="hvv-card" data-stop-id="${frappe.utils.escape_html(s.stop_id)}"
                 style="border:1px solid var(--border-color);border-radius:8px;padding:10px;cursor:pointer;transition:all .15s;">
              <div style="display:flex;justify-content:space-between;gap:8px;">
                <b>${frappe.utils.escape_html(s.stop_name)}</b>
                <span class="text-muted" style="white-space:nowrap;">${Math.round(s.distance_m)} m · ${WALK_SVG} ${walk_min(s.distance_m)} min</span>
              </div>
              <div class="text-muted" style="font-size:12px;margin-top:4px;">
                ${frappe.utils.escape_html(s.type || "")}${s.vehicle_types ? " · " + frappe.utils.escape_html(s.vehicle_types) : ""}
              </div>
              ${s.lines_cache ? `<div style="font-size:12px;margin-top:6px;">${frappe.utils.escape_html(s.lines_cache)}</div>` : ""}
            </div>
        `);
        $card.on("click", () => select_stop(frm, s, $card));
        $cards.append($card);
    });

    if (_state.center_marker) bounds.push(_state.center_marker.getLatLng());
    if (bounds.length > 1) {
        try { _state.map.fitBounds(bounds, { padding: [30, 30] }); } catch (e) { /* ignore */ }
    }
    wrapper.find(".hvv-locsearch-actions").css("display", "flex");
}

async function refresh_search(frm) {
    await ensure_map_ready(frm);
    const address = (frm.doc.last_address || "").trim();
    const radius = cint(frm.doc.radius_m) || 1000;
    if (!address) { set_status(frm, __("Adresse leer.")); return; }

    set_status(frm, `${__("Geocoding")}: ${address} ...`);
    frappe.call({
        method: "hvv_departures.api.endpoints.geocode_address",
        args: { query: address },
        callback: (r) => {
            const candidates = r.message || [];
            if (!candidates.length) {
                set_status(frm, __("Keine Adress-Treffer."));
                _state.station_layer.clearLayers();
                frm.get_field("location_search_html").$wrapper.find(".hvv-station-cards").empty();
                return;
            }
            const addr = candidates[0];
            frm.set_value("center_lat", addr.lat);
            frm.set_value("center_lon", addr.lon);
            set_center(addr.lat, addr.lon, radius);
            set_status(frm, `${__("Treffer")}: ${addr.combined_name || addr.name} — ${__("lade Haltestellen ...")}`);
            frappe.call({
                method: "hvv_departures.api.endpoints.nearby_with_lines",
                args: { lat: addr.lat, lon: addr.lon, radius_m: radius },
                callback: (res) => {
                    const stops = res.message || [];
                    set_status(frm, `${stops.length} ${__("Haltestelle(n) im")} ${radius}m-${__("Umkreis um")} ${addr.combined_name || addr.name}`);
                    render_cards_and_markers(frm, stops);
                },
            });
        },
    });
}

async function search_with_save(frm) {
    if (frm.is_dirty()) {
        try { await frm.save(); } catch (e) { /* save errors shown by Frappe */ }
    }
    refresh_search(frm);
}

frappe.ui.form.on("HVV Settings", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connection"), run_test_connection).addClass("btn-primary");
        ensure_map_ready(frm);
        const addr_input = frm.get_field("last_address").$input;
        if (addr_input && !addr_input.data("hvv-bound")) {
            addr_input.data("hvv-bound", true).on("keydown", (e) => {
                if (e.key === "Enter") { e.preventDefault(); search_with_save(frm); }
            });
        }
    },
    test_connection_btn(frm) { run_test_connection(); },
    search_btn(frm) { search_with_save(frm); },
});
