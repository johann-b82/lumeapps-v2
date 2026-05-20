# lumeapps-v2

ERPNext-based replacement for the legacy lumeapps stack. Two pieces:

| Folder | What |
|---|---|
| `migration/` | Python scripts that import legacy German ERP export files (`Kunden.xlsx`, `Interessenten.txt`, `Aufträge.txt`, `Kontakte.txt`) into ERPNext as Customer / Lead / Sales Order / Communication. Only existing doctype fields, dedupe by stable legacy keys, per-script log file in `logs/` with created/duplicate/failed counts and failure reasons. |
| `sensor_monitor/` | First-class Frappe app for SNMP temperature/humidity logging. DocTypes Sensor, Sensor Reading, Sensor Poll Log, Sensor Monitor Settings. Cron-driven `pysnmp` poller, daily retention purge, whitelisted REST API, live dashboard page with stacked sensor blocks (KPI cards + split temp/humidity charts, dashed yMarkers at the global min/max thresholds). |

## Spin up ERPNext

```bash
docker compose -p erpnext up -d
# wait ~3-5 min for the create-site container to finish
open http://localhost:8080   # Administrator / admin
```

Complete the setup wizard once (Country: Germany, Currency: EUR, Company: any). After that the API is reachable at `http://localhost:8080/api/method/...`.

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

## Install the sensor_monitor app

```bash
docker cp sensor_monitor erpnext-backend-1:/home/frappe/frappe-bench/apps/sensor_monitor
docker compose -p erpnext exec backend bash -lc \
  '/home/frappe/frappe-bench/env/bin/pip install pysnmp -e /home/frappe/frappe-bench/apps/sensor_monitor'
docker compose -p erpnext exec backend bench --site frontend install-app sensor_monitor
```

Pages:

* `/app/sensor-dashboard` — live dashboard, one block per enabled sensor, 30 s auto-refresh.
* `/app/sensor` — list / form for sensors (host, port, OIDs, scales, community).
* `/app/sensor-monitor-settings` — global temperature / humidity min and max thresholds (shown as dashed lines on the dashboard charts).
* `/app/sensor-poll-log`, `/app/sensor-reading` — raw history.

## Notes

* `frappe_docker/` (the upstream Frappe compose helper repo) is gitignored. `docker-compose.yml` at the repo root is the pinned `pwd.yml` from `frappe/frappe_docker` so the stack boots without an extra clone.
* `pysnmp` ≥ 7 is async-first. The poller runs each SNMP GET inside `asyncio.run`, so it works from gunicorn worker threads. `DATETIME` fields are written via raw SQL because Frappe's `DateTime` cast appends a `+00:00` offset that MariaDB rejects.
* Built and verified with Claude Code.
