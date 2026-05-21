from __future__ import annotations
from typing import Any
import requests
import frappe

GRAPH_BASE = "https://graph.facebook.com/v20.0"


class MetaAPIError(Exception):
    def __init__(self, status_code: int, meta_code: int | None, meta_message: str):
        super().__init__(f"Meta API {status_code}: [{meta_code}] {meta_message}")
        self.status_code = status_code
        self.meta_code = meta_code
        self.meta_message = meta_message

    @property
    def retryable(self) -> bool:
        return self.status_code >= 500 or self.status_code == 429


def _settings():
    return frappe.get_single("WhatsApp Settings")


def _headers() -> dict:
    s = _settings()
    token = s.get_password("access_token")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _raise_for(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {}) or {}
        except Exception:
            err = {}
        raise MetaAPIError(
            status_code=resp.status_code,
            meta_code=err.get("code"),
            meta_message=err.get("message", resp.text[:200]),
        )


def send_template(*, to: str, template_name: str, lang: str, components: list[dict]) -> dict[str, Any]:
    s = _settings()
    url = f"{GRAPH_BASE}/{s.phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template_name, "language": {"code": lang}, "components": components},
    }
    r = requests.post(url, json=payload, headers=_headers(), timeout=15)
    _raise_for(r)
    return r.json()


def submit_template(template_dict: dict) -> dict[str, Any]:
    s = _settings()
    url = f"{GRAPH_BASE}/{s.business_account_id}/message_templates"
    r = requests.post(url, json=template_dict, headers=_headers(), timeout=15)
    _raise_for(r)
    return r.json()


def get_template_status(name: str, language: str) -> dict[str, Any]:
    s = _settings()
    url = f"{GRAPH_BASE}/{s.business_account_id}/message_templates"
    r = requests.get(url, params={"name": name}, headers=_headers(), timeout=15)
    _raise_for(r)
    data = r.json().get("data", [])
    for t in data:
        if t.get("name") == name and t.get("language") == language:
            return t
    raise MetaAPIError(404, None, f"template {name}/{language} not found")


def upload_media(file_path: str, mime_type: str) -> str:
    s = _settings()
    url = f"{GRAPH_BASE}/{s.phone_number_id}/media"
    token = s.get_password("access_token")
    with open(file_path, "rb") as fh:
        files = {"file": (file_path.rsplit("/", 1)[-1], fh, mime_type)}
        data = {"messaging_product": "whatsapp", "type": mime_type}
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.post(url, files=files, data=data, headers=headers, timeout=30)
    _raise_for(r)
    return r.json()["id"]
