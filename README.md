# lumeapps-v2

ERPNext-based replacement for the legacy lumeapps stack. Pieces:

| Folder | What |
|---|---|
| `migration/` | Python scripts that import legacy German ERP export files (`Kunden.xlsx`, `Interessenten.txt`, `Aufträge.txt`, `Kontakte.txt`) into ERPNext as Customer / Lead / Sales Order / Communication. Only existing doctype fields, dedupe by stable legacy keys, per-script log file in `logs/` with created/duplicate/failed counts and failure reasons. |
| `sensor_monitor/` | First-class Frappe app for SNMP temperature/humidity logging. DocTypes Sensor, Sensor Reading, Sensor Poll Log, Sensor Monitor Settings. Cron-driven `pysnmp` poller, daily retention purge, whitelisted REST API, live dashboard page with stacked sensor blocks (KPI cards + split temp/humidity area charts, dashed yMarkers at the global min/max thresholds). |
| `whatsapp_broadcast/` | Frappe app for WhatsApp Cloud API broadcast. DocTypes Post / Recipient / Tag / Template / Settings, webhook + Meta client. |
| `hvv_departures/` | Frappe app showing HVV Geofox public-transit stops + live departures around a configurable address. HMAC-SHA1 signed Geofox GTI client, cached stop list filtered to a radius, Desk Page with Leaflet/OSM map and expandable departure cards grouped by direction with HVV-style colored line badges. See [hvv_departures/README.md](hvv_departures/README.md). |

## Spin up ERPNext (custom image, no post-deploy steps)

```bash
make up                # builds lumeapps/erpnext:local + starts the stack
open http://localhost:8080   # Administrator / admin
```

The custom image (see `Dockerfile`) extends `frappe/erpnext:v16.19.1` and bakes in:

* `sensor_monitor` app, editable-installed into the bench env
* `whatsapp_broadcast` app, editable-installed into the bench env
* `hvv_departures` app, editable-installed into the bench env
* `pysnmp>=7.0` (with the app's poller calling the new `v1arch.asyncio.Slim` API under `asyncio.run`)
* `requests>=2.31` for the Geofox client
* `bench build --app <app>` for each in-house app — symlinks + bundled assets are baked, so the nginx container serves logos + page JS without any runtime setup

The `create-site` container runs `bench new-site ... --install-app erpnext --install-app sensor_monitor --install-app whatsapp_broadcast --install-app hvv_departures` automatically, so a fresh `make nuke && make up` lands on a fully working stack.

## Volumes

* `db-data` → docker named volume (case-sensitive ext4 inside the Docker VM; required because macOS bind mounts are case-insensitive and break InnoDB tablespace lookups with `lower_case_table_names=2`).
* `./data/sites` → bench sites (bind mount).
* `./data/logs` → bench logs (bind mount).
* `./data/redis-queue` → redis AOF (bind mount).

## Makefile targets

```
make build         # build lumeapps/erpnext:local
make up            # build + start (detached)
make down          # stop
make restart       # restart frappe services
make ps            # status
make logs s=NAME   # tail a service (default backend)
make shell         # bash into backend
make bench c='...' # run any bench command on the frontend site
make install-app   # install sensor_monitor on existing site
make migrate       # bench --site frontend migrate
make clear-cache   # clear app + website cache
make fresh         # wipe sites/logs/redis bind dirs and re-create the site (keeps DB)
make nuke          # also drop the DB volume — full reset
```

## Run the legacy importer

```bash
pip3 install requests openpyxl
export ERP_URL=http://localhost:8080 ERP_USER=Administrator ERP_PASS=admin
python3 migration/run_all.py
```

Sample run on the included dataset produced:

| Doctype | created | duplicates | failed | top failure reason |
|---|---|---|---|---|
| Customer | 623 | 35 | 0 | — |
| Lead | 1669 | 29 | 106 | invalid email / phone |
| Communication | 13972 | 0 | 0 | — |
| Sales Order | 42354 | 0 | 1057 | 699 missing customer, 358 negative total |

Each script writes a structured log to `logs/<script>.log`.

## sensor_monitor pages

* `/app/sensor-dashboard` — live dashboard, one block per enabled sensor, 30 s auto-refresh. Area charts (temperature in amber `#f59e0b`, humidity in sky `#0ea5e9`), red dashed yMarker lines at the global min/max thresholds. Health pill shows `Last updated: DD.MM.YYYY HH:MM:SS`.
* `/app/sensor` — list / form for sensors (host, port, OIDs, scales, community). `scale` is a multiplier: raw × scale = engineering value (for 0.1°C units enter `0.1`).
* `/app/sensor-monitor-settings` — global temperature / humidity min and max thresholds (shown as red dashed lines on the dashboard charts).
* `/app/sensor-poll-log`, `/app/sensor-reading` — raw history.

The app's Workspace and Desktop Icon are populated with the thermometer logo via `after_install` and re-applied on every `bench migrate` via `after_migrate`, so the sidebar app chip always renders the SVG instead of falling back to the workspace-title initial.

## Sample data policy

Legacy ERP exports (`Imports/`, `Kunden.xlsx`, `Interessenten.txt`, `Aufträge.txt`, `Kontakte.txt`, any `*.xlsx`) and runtime bind mounts (`data/`, `logs/`) are **gitignored and must never be committed**. They may contain customer-identifiable data. Future contributions: keep sample / customer data out of the repo, and add new ignore patterns to `.gitignore` rather than working around them.

## Notes

* `frappe_docker/` (the upstream Frappe compose helper repo) is gitignored.
* `pysnmp` ≥ 7 is async-first. The poller runs each SNMP GET inside `asyncio.run`, so it works from gunicorn worker threads. `DATETIME` fields are written via raw SQL because Frappe's `DateTime` cast appends a `+00:00` offset that MariaDB rejects.
* Built and verified with Claude Code.

## WhatsApp Broadcast app

Frappe app `whatsapp_broadcast` adds WhatsApp Cloud API template broadcasting.

1. Configure **WhatsApp Settings** (`/app/whatsapp-settings`):
   - `phone_number_id`, `business_account_id`, `access_token` (from Meta Business Manager).
   - `webhook_verify_token`, `app_secret` (set up the webhook in Meta first; use any string for verify token).
2. In Meta Business Manager → WhatsApp → Configuration, set webhook URL to:
   `https://<your-host>/api/method/whatsapp_broadcast.api.webhook.handle`
   Verify token = the value in Settings. Subscribe to `messages` field.
3. Create **WhatsApp Templates**, hit **Submit to Meta**, wait for Meta approval (use **Sync Status** to refresh).
4. Add **WhatsApp Recipients** with E.164 phone numbers and tag them.
5. Create a **WhatsApp Post**, pick template + fill variables + select tags or recipients, **Send**.

Run tests:

```bash
docker compose -p erpnext exec backend bench --site frontend run-tests --app whatsapp_broadcast
```

