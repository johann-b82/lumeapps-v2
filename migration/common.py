"""Shared utilities for migration scripts.

Reads German legacy export files (ISO-8859 tab-separated with `="..."` quoted
text fields) and talks to a running ERPNext instance via REST API.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import requests

ROOT = Path(__file__).resolve().parent.parent
IMPORTS = ROOT / "Imports"
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

ERP_URL = os.environ.get("ERP_URL", "http://localhost:8080")
ERP_USER = os.environ.get("ERP_USER", "Administrator")
ERP_PASS = os.environ.get("ERP_PASS", "admin")


_QUOTED = re.compile(r'^="(.*)"$', re.DOTALL)


def unquote(val: Any) -> Any:
    """Strip the `="..."` wrapper used by the legacy exporter."""
    if val is None:
        return None
    if not isinstance(val, str):
        return val
    s = val.strip()
    m = _QUOTED.match(s)
    if m:
        s = m.group(1)
    return s.strip()


def read_legacy_tsv(path: Path, encoding: str = "iso-8859-1") -> Iterator[dict]:
    """Yield row dicts from a legacy `="..."` tab-separated export."""
    with open(path, "r", encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = [unquote(c) for c in next(reader)]
        for raw in reader:
            if not raw or all(not c for c in raw):
                continue
            row = {h: unquote(v) for h, v in zip(header, raw)}
            yield row


def read_legacy_xlsx(path: Path) -> Iterator[dict]:
    """Yield row dicts from a legacy `="..."` xlsx (Kunden.xlsx style)."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [unquote(c) for c in next(rows)]
    for raw in rows:
        if raw is None or all(c is None or c == "" for c in raw):
            continue
        yield {h: unquote(v) for h, v in zip(header, raw)}


def parse_de_date(val: str | None) -> str | None:
    """Convert '19.12.2000' -> '2000-12-19' (ERPNext ISO format)."""
    if not val:
        return None
    val = val.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.strptime(val, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_de_decimal(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


# -------- ERPNext client --------

@dataclass
class Stats:
    name: str
    created: int = 0
    duplicates: int = 0
    failed: int = 0
    skipped: int = 0
    reasons: dict = field(default_factory=dict)

    def fail(self, reason: str) -> None:
        self.failed += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def summary(self) -> str:
        return (
            f"[{self.name}] created={self.created} duplicates={self.duplicates} "
            f"failed={self.failed} skipped={self.skipped} reasons={json.dumps(self.reasons, ensure_ascii=False)}"
        )


class ERPClient:
    def __init__(self, url: str = ERP_URL, user: str = ERP_USER, pwd: str = ERP_PASS):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-Frappe-CSRF-Token": "token"})
        self._login(user, pwd)

    def _login(self, user: str, pwd: str) -> None:
        r = self.session.post(
            f"{self.url}/api/method/login",
            data={"usr": user, "pwd": pwd},
            timeout=60,
        )
        r.raise_for_status()

    def exists(self, doctype: str, name: str) -> bool:
        r = self.session.get(
            f"{self.url}/api/resource/{doctype}/{requests.utils.quote(name, safe='')}",
            timeout=60,
        )
        return r.status_code == 200

    def find_one(self, doctype: str, filters: dict, fields: list[str] | None = None) -> dict | None:
        params = {
            "filters": json.dumps([[k, "=", v] for k, v in filters.items()]),
            "fields": json.dumps(fields or ["name"]),
            "limit_page_length": 1,
        }
        r = self.session.get(f"{self.url}/api/resource/{doctype}", params=params, timeout=60)
        if r.status_code != 200:
            return None
        data = r.json().get("data") or []
        return data[0] if data else None

    def insert(self, doctype: str, payload: dict) -> tuple[bool, str]:
        body = {"doctype": doctype, **payload}
        r = self.session.post(
            f"{self.url}/api/resource/{doctype}",
            data={"data": json.dumps(body, ensure_ascii=False)},
            timeout=120,
        )
        if r.status_code in (200, 201):
            return True, r.json().get("data", {}).get("name", "")
        msg = ""
        try:
            j = r.json()
            msg = j.get("exception") or j.get("_server_messages") or j.get("message") or r.text
        except Exception:
            msg = r.text
        return False, f"HTTP {r.status_code}: {str(msg)[:300]}"


def make_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fh = logging.FileHandler(LOGS / f"{name}.log", encoding="utf-8", mode="w")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(sh)
    return logger


def wait_for_erp(url: str = ERP_URL, timeout: int = 600) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/api/method/ping", timeout=5)
            if r.status_code == 200:
                return
            last = f"{r.status_code}"
        except Exception as e:
            last = str(e)
        time.sleep(5)
    raise RuntimeError(f"ERPNext not reachable at {url}: {last}")
