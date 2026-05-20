"""Import sales orders (20260430_Aufträge.txt) into ERPNext Sales Order.

Legacy file has no per-line items, only an order total. We create one line
using a generic placeholder Item (must exist) with qty=1 and rate=order value.
Customer must already exist (matched by Name). Dedupe by legacy order id stored
in `po_no` (Customer's Purchase Order field — existing Sales Order field).
"""
from __future__ import annotations

from common import (
    ERPClient, IMPORTS, Stats, make_logger, parse_de_date, parse_de_decimal,
    read_legacy_tsv, wait_for_erp,
)

LOG = make_logger("import_orders")

PLACEHOLDER_ITEM = "LEGACY-IMPORT"


def ensure_placeholder_item(erp: ERPClient) -> None:
    if erp.exists("Item", PLACEHOLDER_ITEM):
        return
    ok, info = erp.insert("Item", {
        "item_code": PLACEHOLDER_ITEM,
        "item_name": "Legacy Import Line",
        "item_group": "All Item Groups",
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "include_item_in_manufacturing": 0,
    })
    if not ok:
        raise RuntimeError(f"failed to create placeholder Item: {info}")


def map_row(row: dict) -> tuple[dict | None, str | None]:
    legacy_id = (row.get("Nummer") or "").strip()
    customer = (row.get("Name") or "").strip()
    if not customer or not legacy_id:
        return None, "missing customer/legacy_id"
    amount = parse_de_decimal(row.get("Wert"))
    if amount is None:
        amount = 0.0
    date = parse_de_date(row.get("Datum"))
    if not date:
        return None, "missing date"
    so = {
        "customer": customer,
        "transaction_date": date,
        "delivery_date": date,
        "currency": "EUR",
        "po_no": f"LEGACY-{legacy_id}",
        "items": [{
            "item_code": PLACEHOLDER_ITEM,
            "qty": 1,
            "rate": amount,
            "delivery_date": date,
        }],
    }
    return so, None


def main() -> None:
    wait_for_erp()
    erp = ERPClient()
    ensure_placeholder_item(erp)
    stats = Stats("orders")
    customer_cache: dict[str, bool] = {}
    seen_legacy: set[str] = set()
    for row in read_legacy_tsv(IMPORTS / "20260430_Aufträge.txt"):
        legacy_id = (row.get("Nummer") or "").strip()
        if legacy_id in seen_legacy:
            stats.duplicates += 1
            LOG.info("duplicate legacy_id=%s", legacy_id)
            continue
        payload, err = map_row(row)
        if not payload:
            stats.skipped += 1
            LOG.info("skip legacy_id=%s reason=%s", legacy_id, err)
            continue
        cust = payload["customer"]
        present = customer_cache.get(cust)
        if present is None:
            present = erp.exists("Customer", cust)
            customer_cache[cust] = present
        if not present:
            stats.fail("customer_missing")
            LOG.error("missing customer=%s legacy_id=%s", cust, legacy_id)
            continue
        # dedupe by po_no already-in-ERP
        existing = erp.find_one("Sales Order", {"po_no": payload["po_no"]})
        if existing:
            stats.duplicates += 1
            seen_legacy.add(legacy_id)
            LOG.info("duplicate (in ERP) po_no=%s", payload["po_no"])
            continue
        ok, info = erp.insert("Sales Order", payload)
        if ok:
            stats.created += 1
            seen_legacy.add(legacy_id)
            LOG.info("created SO name=%s legacy_id=%s", info, legacy_id)
        else:
            stats.fail(info.split(":")[0] if ":" in info else info[:80])
            LOG.error("failed SO legacy_id=%s err=%s", legacy_id, info)
    LOG.info(stats.summary())
    print(stats.summary())


if __name__ == "__main__":
    main()
