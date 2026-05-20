"""Import customers from Imports/Kunden.xlsx into ERPNext Customer doctype.

Only existing default fields are used. Duplicates are detected by customer_name.
Run: python3 migration/import_customers.py
"""
from __future__ import annotations

from common import (
    ERPClient, IMPORTS, Stats, make_logger, read_legacy_xlsx, wait_for_erp,
)

LOG = make_logger("import_customers")

GROUP_MAP = {
    "MRO": "Commercial",
    "OEM": "Commercial",
    "AL":  "Commercial",
}


def map_row(row: dict) -> dict | None:
    name = (row.get("Name 1") or "").strip()
    if not name:
        return None
    territory = (row.get("Land") or "").strip() or "All Territories"
    tax_id = (row.get("UmsatzSteuerIdnr") or "").strip() or None
    customer = {
        "customer_name": name,
        "customer_type": "Company",
        "customer_group": "Commercial",
        "territory": "All Territories",
        "tax_id": tax_id,
        "language": "de",
    }
    # store legacy id in disabled-by-default "customer_pos_id" if exists, else skip.
    return customer


def main() -> None:
    wait_for_erp()
    erp = ERPClient()
    stats = Stats("customers")
    seen: set[str] = set()
    for row in read_legacy_xlsx(IMPORTS / "Kunden.xlsx"):
        payload = map_row(row)
        if not payload:
            stats.skipped += 1
            LOG.info("skip empty name row legacy_id=%s", row.get("Nummer"))
            continue
        cname = payload["customer_name"]
        if cname in seen or erp.exists("Customer", cname):
            stats.duplicates += 1
            LOG.info("duplicate customer_name=%s legacy_id=%s", cname, row.get("Nummer"))
            seen.add(cname)
            continue
        ok, info = erp.insert("Customer", payload)
        if ok:
            stats.created += 1
            seen.add(cname)
            LOG.info("created Customer name=%s legacy_id=%s", info, row.get("Nummer"))
        else:
            stats.fail(info.split(":")[0] if ":" in info else info[:80])
            LOG.error("failed Customer name=%s legacy_id=%s err=%s", cname, row.get("Nummer"), info)
    LOG.info(stats.summary())
    print(stats.summary())


if __name__ == "__main__":
    main()
