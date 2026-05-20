"""Import CRM activities (20260430_Kontakte.txt) into ERPNext.

Each legacy contact log row -> ERPNext "Communication" doc (existing doctype),
which is the universal activity log in ERPNext. Only existing default fields
used. Dedupe by (date, sender, subject) tuple.
"""
from __future__ import annotations

import hashlib

from common import (
    ERPClient, IMPORTS, Stats, make_logger, parse_de_date, read_legacy_tsv,
    wait_for_erp,
)

LOG = make_logger("import_activities")


def map_row(row: dict) -> dict | None:
    date = parse_de_date(row.get("Datum"))
    if not date:
        return None
    subject = (row.get("Kommentar") or "").strip() or f"Activity {row.get('VrgID', '')}"
    content = (
        f"Legacy CRM activity\n"
        f"User: {row.get('Wer') or ''}\n"
        f"Group: {row.get('Gruppe') or ''}\n"
        f"Customer: {row.get('Name') or ''} ({row.get('PLZ') or ''} {row.get('Ort') or ''})\n"
        f"Branche: {row.get('Branche') or ''}\n"
        f"Time: {row.get('Zeit') or ''}\n"
        f"Comment: {row.get('Kommentar') or ''}\n"
    )
    return {
        "subject": subject[:140],
        "content": content,
        "communication_type": "Communication",
        "communication_medium": "Other",
        "sent_or_received": "Sent",
        "communication_date": date,
        "sender_full_name": (row.get("Wer") or "").strip() or None,
        "status": "Closed",
    }


def main() -> None:
    wait_for_erp()
    erp = ERPClient()
    stats = Stats("activities")
    seen: set[str] = set()
    for row in read_legacy_tsv(IMPORTS / "20260430_Kontakte.txt"):
        payload = map_row(row)
        if not payload:
            stats.skipped += 1
            LOG.info("skip empty date row VrgID=%s", row.get("VrgID"))
            continue
        sig = hashlib.md5(
            f"{payload['communication_date']}|{payload['sender_full_name']}|{payload['subject']}|{row.get('VrgID','')}".encode()
        ).hexdigest()
        if sig in seen:
            stats.duplicates += 1
            LOG.info("duplicate VrgID=%s subject=%s", row.get("VrgID"), payload["subject"])
            continue
        ok, info = erp.insert("Communication", {k: v for k, v in payload.items() if v is not None})
        if ok:
            stats.created += 1
            seen.add(sig)
            LOG.info("created Communication name=%s VrgID=%s", info, row.get("VrgID"))
        else:
            stats.fail(info.split(":")[0] if ":" in info else info[:80])
            LOG.error("failed Communication VrgID=%s err=%s", row.get("VrgID"), info)
    LOG.info(stats.summary())
    print(stats.summary())


if __name__ == "__main__":
    main()
