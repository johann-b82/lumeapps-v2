"""Import prospects (Interessenten.txt) into ERPNext Lead doctype.

Only existing default Lead fields are used. Dedupe by company_name.
"""
from __future__ import annotations

from common import (
    ERPClient, IMPORTS, Stats, make_logger, read_legacy_tsv, wait_for_erp,
)

LOG = make_logger("import_prospects")


def map_row(row: dict) -> dict | None:
    company = (row.get("Name 1") or "").strip()
    if not company:
        return None
    first_name = (row.get("Vorname") or "").strip()
    lead = {
        "lead_name": first_name or company,
        "company_name": company,
        "status": "Lead",
        "email_id": (row.get("E-Mail") or "").strip() or None,
        "phone": (row.get("Telefon") or "").strip() or None,
        "fax": (row.get("Telefax") or "").strip() or None,
        "city": (row.get("Ort") or "").strip() or None,
        "country": map_country(row.get("Land")),
        "no_of_employees": None,
        "source": "Existing Customer",
        "territory": "All Territories",
    }
    return {k: v for k, v in lead.items() if v is not None}


COUNTRY = {"D": "Germany", "DE": "Germany", "AT": "Austria", "CH": "Switzerland",
           "SLO": "Slovenia", "SI": "Slovenia", "UAE": "United Arab Emirates",
           "F": "France", "FR": "France", "I": "Italy", "IT": "Italy",
           "UK": "United Kingdom", "GB": "United Kingdom", "US": "United States",
           "USA": "United States", "NL": "Netherlands", "B": "Belgium",
           "BE": "Belgium", "ES": "Spain", "PL": "Poland", "CZ": "Czech Republic"}


def map_country(code: str | None) -> str | None:
    if not code:
        return None
    return COUNTRY.get(code.strip().upper())


def main() -> None:
    wait_for_erp()
    erp = ERPClient()
    stats = Stats("prospects")
    seen: set[str] = set()
    for row in read_legacy_tsv(IMPORTS / "Interessenten.txt"):
        payload = map_row(row)
        if not payload:
            stats.skipped += 1
            LOG.info("skip empty row legacy_id=%s", row.get("Nummer"))
            continue
        key = payload["company_name"]
        if key in seen:
            stats.duplicates += 1
            LOG.info("duplicate company_name=%s legacy_id=%s", key, row.get("Nummer"))
            continue
        existing = erp.find_one("Lead", {"company_name": key})
        if existing:
            stats.duplicates += 1
            seen.add(key)
            LOG.info("duplicate (already in ERP) company_name=%s legacy_id=%s", key, row.get("Nummer"))
            continue
        ok, info = erp.insert("Lead", payload)
        if ok:
            stats.created += 1
            seen.add(key)
            LOG.info("created Lead name=%s legacy_id=%s", info, row.get("Nummer"))
        else:
            stats.fail(info.split(":")[0] if ":" in info else info[:80])
            LOG.error("failed Lead company=%s legacy_id=%s err=%s", key, row.get("Nummer"), info)
    LOG.info(stats.summary())
    print(stats.summary())


if __name__ == "__main__":
    main()
