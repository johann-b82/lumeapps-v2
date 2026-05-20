# Migration Scripts

Import legacy data from `../Imports/` into a running ERPNext instance.

## ERPNext setup

```bash
git clone --depth 1 https://github.com/frappe/frappe_docker.git
cd frappe_docker
docker compose -f pwd.yml -p erpnext up -d
# wait ~3-5 min for create-site to finish, then open http://localhost:8080
# default credentials: Administrator / admin
```

Verify: `curl -s http://localhost:8080/api/method/ping` should return `{"message":"pong"}`.

## Run imports

```bash
pip3 install requests openpyxl
export ERP_URL=http://localhost:8080
export ERP_USER=Administrator
export ERP_PASS=admin

python3 migration/run_all.py
# or individually:
python3 migration/import_customers.py
python3 migration/import_prospects.py
python3 migration/import_orders.py
python3 migration/import_activities.py
```

Logs and statistics go to `../logs/<script>.log`.

## File → Doctype mapping

| Source file | ERPNext Doctype | Dedupe key |
|---|---|---|
| `Kunden.xlsx` | Customer | `customer_name` |
| `Interessenten.txt` | Lead | `company_name` |
| `20260430_Aufträge.txt` | Sales Order | `po_no` = `LEGACY-<Nummer>` |
| `20260430_Kontakte.txt` | Communication | hash(date+sender+subject+VrgID) |

Only standard ERPNext fields are used. No schema changes.

## Notes

* Sales Orders need a placeholder `Item` named `LEGACY-IMPORT` — created on first run.
* Legacy orders have only a total, not per-line items; total is stored as line rate with qty=1.
* Currency assumed `EUR`. Adjust in `import_orders.py` if needed.
* Customers must be imported before orders (foreign-key requirement).
