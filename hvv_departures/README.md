# HVV Departures

First-class Frappe app for **Hamburg HVV public-transit data**: shows nearby
stops + live departures around a configurable address, using the
[Geofox GTI](https://gti.geofox.de) signed REST API.

## What it does

* **Address-based search.** Enter an address in `HVV Settings`, press *Suchen*
  → the app geocodes via Geofox `checkName`, drops a marker + radius circle on
  a Leaflet/OSM map, and lists nearby HVV stops as clickable cards.
* **Cached stop list (`HVV Stop` doctype).** Pulled from Geofox `listStations`,
  filtered to the configured center + radius. Re-syncing prunes everything
  outside the radius via a single bulk SQL `DELETE`.
* **Per-stop line summary.** For each stop, departures are sampled once via
  `departureList` and the unique line names + directions are cached on
  `HVV Stop.lines_cache` (semicolon list `"21 → Teufelsbrück; M3 → ..."`).
* **Live departures Desk page (`/app/hvv-map`).** Each stop is rendered as a
  collapsible card. Expanded view shows columns grouped by
  `(line × direction)` with the real departure time (timeOffset + delay) and
  an HVV-style colored badge:
    * **Hexagon** for buses (numeric, `M…`, `X…`, `N…`, `Regional…`,
      Schnellbus, Nachtbus, Fähre).
    * **Rounded rectangle** for U-Bahn / S-Bahn / AKN / R-Bahn.
    * Per-line override colors (`U1`–`U5`, `S1`–`S5`, `S11`/`S21`/`S31`,
      `A1`–`A3`) plus a fallback type→color map.
    * Type is inferred from the line name prefix when Geofox omits it,
      so badges look right *before* the first departure fetch.
* **Connection test.** *Test Connection* button on `HVV Settings` pings
  Geofox `/init` and prints version + service window or the exact error /
  return code.

## Architecture

```
hvv_departures/
├── hooks.py                      app metadata, desktop icon hooks
├── install.py                    Desktop Icon ensure
├── requirements.txt              requests
├── api/
│   ├── geofox.py                 HMAC-SHA1 signed client, sync, haversine
│   └── endpoints.py              @frappe.whitelist wrappers for the Desk JS
└── hvv_departures/
    ├── doctype/
    │   ├── hvv_settings/         Single doctype: creds, address, radius,
    │   │                         time-horizon, hidden center lat/lon,
    │   │                         search button, default stop, custom JS
    │   │                         with Leaflet map + station cards + actions.
    │   └── hvv_stop/             Per-station cache (id, name, city, lat/lon,
    │                             vehicle types, lines_cache, last_synced).
    │                             List view: "Stationen synchronisieren"
    │                             button (radius-scoped + cleanup).
    ├── page/hvv_map/             Desk page `/app/hvv-map` (Leaflet, badges,
    │                             expand-/collapse-able cards, departure
    │                             columns grouped by direction).
    ├── workspace/hvv_departures/ Workspace `/app/hvv-departures`.
    └── public/images/            App logo.
```

### Geofox client

`api/geofox.py`:

* **Signature.** `geofox-auth-signature` header is
  `base64(HMAC-SHA1(password, json_body))`, `geofox-auth-user` carries the
  username, `geofox-auth-type` is `HmacSHA1`. All requests POST JSON to
  `https://gti.geofox.de/gti/public/<method>`.
* **Methods used:** `init`, `checkName`, `listStations` (with
  `coordinateType: "EPSG_4326"` so each station has a real WGS84
  `coordinate.{x,y}`), `departureList` (real `{date: "DD.MM.YYYY",
  time: "HH:MM"}` — Geofox rejects `"today"/"now"`).
* **`sync_stations()`.** Pulls the full ~16k-row list, filters by haversine
  to the configured radius, upserts the survivors, then bulk-deletes
  anything outside via a single SQL statement (per-row `frappe.delete_doc`
  was too slow + caused lock-wait timeouts).
* **`haversine_m()`.** Geo distance helper, reused by both sync + the
  `nearby_*` endpoints.

### Whitelisted endpoints (`api/endpoints.py`)

| method | purpose |
|---|---|
| `test_connection` | Calls `init`, returns `{ok, version, build, …}`. |
| `get_center` | Returns the configured center + radius for the Leaflet view. |
| `sync_stations` | Re-fetches the list with cleanup, returns counts. |
| `geocode_address(query)` | Returns Geofox `checkName` candidates. |
| `nearby_stations(lat?, lon?, radius_m?)` | Lightweight filter from the cached `HVV Stop` table. |
| `nearby_with_lines(lat?, lon?, radius_m?, refresh_lines=1)` | Same, plus a one-time `departureList` per stop to fill `lines_cache`. |
| `search_stops(query, limit)` | Autocomplete over `HVV Stop`. |
| `departures(station_id, max_results=20, max_time_offset?)` | Live departures; `max_time_offset` defaults to `HVV Settings.time_horizon_minutes`. |

### HVV Settings (Single doctype)

| Field | Use |
|---|---|
| `username` / `password` (HMAC key) | Geofox auth |
| `base_url` | Default `https://gti.geofox.de` |
| `test_connection_btn` | Triggers `test_connection` |
| `last_address` | Search input, default `Brandstücken 16, Hamburg` |
| `radius_m` | Search/sync radius, default `1000` |
| `time_horizon_minutes` | `maxTimeOffset` for `departureList`, default `120` |
| `search_btn` | Auto-saves the form (if dirty) then runs geocode + nearby search |
| `default_stop` | Optional favorite, Link to `HVV Stop` |
| `location_search_html` | Embedded Leaflet map + station-card grid + actions |
| `center_lat` / `center_lon` (hidden, read-only) | Filled by the geocoder, consumed by the map page + sync |

The cards inside the form support:

* Clicking a card → highlights it + opens the Leaflet popup
* **Auf Karte anzeigen** → routes to `/app/hvv-map?stop=<id>` (focuses + auto-expands that stop)
* **Als Default Stop speichern** → sets `default_stop` and saves the form

### Desk page `/app/hvv-map`

* `Stationen synchronisieren` → triggers `sync_stations` (radius-scoped).
* `Aktualisieren` → re-fetches `nearby_with_lines` and re-renders.
* `Stop suchen` → searchable Link control over all cached `HVV Stop` rows.
  Picking a stop scrolls + expands its card (or renders a single-row card
  if the stop is outside the current radius).
* **Karte anzeigen / verbergen** → toggles the Leaflet map (collapsed by
  default; `map.invalidateSize()` runs on first show).
* Each station card:
    * Header row: line badges · stop name · distance · 🚶 walking-time
      (80 m/min) · *Abfahrten ▼* button.
    * Body (auto-expanded by default): one column per `(line × direction)`,
      each listing the departure time + any delay.
    * Clicking anywhere in the header toggles the body. The chevron flips
      ▼ → ▲ accordingly.

## Quick start (inside the lumeapps-v2 stack)

The app is part of `Dockerfile` + `docker-compose.yml`, so:

```bash
make up    # builds the image with hvv_departures baked in + starts the stack
open http://localhost:8080
# Administrator / admin
```

then in the Desk:

1. Go to `/app/hvv-settings`
2. Enter your Geofox **Username** + **Password (HMAC Key)**
3. Click **Test Connection** — should turn green
4. Adjust **Adresse**, **Umkreis**, **Zeithorizont**, hit **Suchen**
5. Go to `/app/hvv-stop` → **Stationen synchronisieren** (one-off; can be
   repeated whenever you change the center or radius)
6. Open `/app/hvv-map`

## Security

* Geofox credentials live only on `HVV Settings` (a Password field, so they
  are stored encrypted by Frappe). The login and the API key reach the
  browser only via the form when authenticated as System Manager.
* The frontend calls **whitelisted, server-side wrappers** — no client ever
  sees the HMAC key.
* Rotate the Geofox password if it ever leaks (e.g. shared in a chat with
  Claude during development); the only place the new password has to be
  pasted is the `HVV Settings` doctype.

## License

MIT (see `license.txt`).
