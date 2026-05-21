# WhatsApp Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Frappe app `whatsapp_broadcast` that lets authorized users compose and send WhatsApp template messages to a managed recipient list via the official Meta WhatsApp Cloud API, with queue-based rate-limited delivery and per-recipient status tracking.

**Architecture:** Standalone Frappe app baked into the existing ERPNext Docker image alongside `sensor_monitor`. Pure-Python `meta_client` wrapper for Graph API (fully unit-testable with `responses`). DocTypes for Settings/Recipient/Tag/Template/Post/Message Log. RQ background workers for fan-out send with Redis token-bucket throttle. Whitelisted webhook endpoint with HMAC verification consumes Meta status events. Custom JS on the Post form provides live preview and realtime progress.

**Tech Stack:** Frappe v16, Python 3.11, ERPNext v16.19.1, Redis (already in stack), `requests` (already in Frappe env), `responses` (test-only), standard Frappe RQ, vanilla JS for the Post form client script.

---

## File Structure

New app at repo root: `whatsapp_broadcast/` (sibling of `sensor_monitor/`).

```
whatsapp_broadcast/
├── pyproject.toml
├── license.txt
├── README.md
└── whatsapp_broadcast/
    ├── __init__.py                       # __version__
    ├── hooks.py                          # app metadata, fixtures, workspace
    ├── modules.txt                       # "WhatsApp Broadcast"
    ├── install.py                        # after_install: create roles + workspace icon
    ├── patches.txt
    ├── requirements.txt                  # (empty; deps in pyproject)
    ├── api/
    │   ├── __init__.py
    │   ├── meta_client.py                # Graph API wrapper, MetaAPIError
    │   ├── webhook.py                    # whitelisted GET/POST handler
    │   └── post_helpers.py               # whitelisted helpers used by Post form JS
    ├── tasks/
    │   ├── __init__.py
    │   ├── token_bucket.py               # Redis token-bucket throttle
    │   └── sender.py                     # send_post + send_single RQ jobs
    ├── public/
    │   └── js/
    │       └── whatsapp_post.js          # custom form script (preview + realtime)
    ├── fixtures/
    │   └── role.json                     # WhatsApp Manager, WhatsApp User
    ├── whatsapp_broadcast/               # module folder (matches modules.txt)
    │   ├── __init__.py
    │   ├── doctype/
    │   │   ├── __init__.py
    │   │   ├── whatsapp_settings/
    │   │   ├── whatsapp_tag/
    │   │   ├── whatsapp_recipient/
    │   │   ├── whatsapp_recipient_tag/        # child for tags MultiSelect
    │   │   ├── whatsapp_template/
    │   │   ├── whatsapp_template_button/      # child
    │   │   ├── whatsapp_post/
    │   │   ├── whatsapp_post_tag/             # child for recipient_tags
    │   │   ├── whatsapp_post_recipient/       # child for explicit_recipients
    │   │   └── whatsapp_message_log/
    │   └── workspace/
    │       └── whatsapp_broadcast/            # workspace JSON
    └── tests/
        ├── __init__.py
        ├── test_meta_client.py
        ├── test_token_bucket.py
        ├── test_webhook.py
        ├── test_template_validation.py
        ├── test_recipient_expansion.py
        ├── test_post_validation.py
        └── test_send_integration.py
```

Repo-level changes:
- `Dockerfile`: copy and install `whatsapp_broadcast` analogous to `sensor_monitor`.
- `docker-compose.yml`: extend `create-site` command with `--install-app whatsapp_broadcast`.
- `Makefile`: extend `install-app` target.

---

## Task 1: Scaffold app + bake into Docker image

**Files:**
- Create: `whatsapp_broadcast/pyproject.toml`
- Create: `whatsapp_broadcast/license.txt`
- Create: `whatsapp_broadcast/README.md`
- Create: `whatsapp_broadcast/whatsapp_broadcast/__init__.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/hooks.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/modules.txt`
- Create: `whatsapp_broadcast/whatsapp_broadcast/patches.txt`
- Create: `whatsapp_broadcast/whatsapp_broadcast/requirements.txt`
- Create: `whatsapp_broadcast/whatsapp_broadcast/install.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/__init__.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/__init__.py`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `Makefile`

- [ ] **Step 1: Create app scaffold files**

`whatsapp_broadcast/pyproject.toml`:
```toml
[project]
name = "whatsapp_broadcast"
version = "0.0.1"
description = "WhatsApp Cloud API broadcast app for ERPNext"
requires-python = ">=3.10"
readme = "README.md"
dynamic = ["dependencies"]

[build-system]
requires = ["flit_core >=3.4,<4"]
build-backend = "flit_core.buildapi"

[tool.flit.module]
name = "whatsapp_broadcast"
```

`whatsapp_broadcast/license.txt`: `MIT`

`whatsapp_broadcast/README.md`:
```markdown
# whatsapp_broadcast
Frappe app: send WhatsApp Cloud API template messages to a managed recipient list.
```

`whatsapp_broadcast/whatsapp_broadcast/__init__.py`:
```python
__version__ = "0.0.1"
```

`whatsapp_broadcast/whatsapp_broadcast/modules.txt`:
```
WhatsApp Broadcast
```

`whatsapp_broadcast/whatsapp_broadcast/patches.txt`: empty file.

`whatsapp_broadcast/whatsapp_broadcast/requirements.txt`: empty file.

`whatsapp_broadcast/whatsapp_broadcast/hooks.py`:
```python
app_name = "whatsapp_broadcast"
app_title = "WhatsApp Broadcast"
app_publisher = "Lume"
app_description = "WhatsApp Cloud API broadcast app"
app_email = "admin@example.com"
app_license = "mit"

add_to_apps_screen = [
    {
        "name": "whatsapp_broadcast",
        "title": "WhatsApp Broadcast",
        "route": "/app/whatsapp-broadcast",
    }
]

fixtures = [
    {"dt": "Role", "filters": [["role_name", "in", ["WhatsApp Manager", "WhatsApp User"]]]},
]

doctype_js = {
    "WhatsApp Post": "public/js/whatsapp_post.js",
}

after_install = "whatsapp_broadcast.install.after_install"
```

`whatsapp_broadcast/whatsapp_broadcast/install.py`:
```python
import frappe


def after_install():
    _ensure_role("WhatsApp Manager")
    _ensure_role("WhatsApp User")


def _ensure_role(role_name: str) -> None:
    if not frappe.db.exists("Role", role_name):
        frappe.get_doc({"doctype": "Role", "role_name": role_name, "desk_access": 1}).insert(
            ignore_permissions=True
        )
```

Empty `__init__.py` files for `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/__init__.py` and `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/__init__.py`.

- [ ] **Step 2: Extend Dockerfile**

Append after the existing `sensor_monitor` block in `Dockerfile`:

```dockerfile
COPY --chown=frappe:frappe whatsapp_broadcast /home/frappe/frappe-bench/apps/whatsapp_broadcast

RUN /home/frappe/frappe-bench/env/bin/pip install --no-cache-dir \
        -e /home/frappe/frappe-bench/apps/whatsapp_broadcast \
    && printf '\nwhatsapp_broadcast\n' >> /home/frappe/frappe-bench/sites/apps.txt \
    && sort -u /home/frappe/frappe-bench/sites/apps.txt -o /home/frappe/frappe-bench/sites/apps.txt \
    && sed -i '/^$/d' /home/frappe/frappe-bench/sites/apps.txt \
    && ln -sf /home/frappe/frappe-bench/apps/whatsapp_broadcast/whatsapp_broadcast/public \
              /home/frappe/frappe-bench/assets/whatsapp_broadcast \
    && cd /home/frappe/frappe-bench \
    && bench build --app whatsapp_broadcast
```

- [ ] **Step 3: Extend docker-compose create-site step**

In `docker-compose.yml`, find the `create-site` service's command (it currently runs `bench new-site ... --install-app erpnext --install-app sensor_monitor`). Append `--install-app whatsapp_broadcast`.

- [ ] **Step 4: Extend Makefile**

In `Makefile`, find the `install-app` target. Add a second `bench --site frontend install-app whatsapp_broadcast` line after the `sensor_monitor` install.

- [ ] **Step 5: Verify build**

Run:
```bash
make nuke && make up
```
Expected: image builds, site comes up, both apps installed. Then:
```bash
docker compose exec backend bench --site frontend list-apps
```
Expected output includes both `sensor_monitor` and `whatsapp_broadcast`.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_broadcast Dockerfile docker-compose.yml Makefile
git commit -m "feat(whatsapp): scaffold whatsapp_broadcast Frappe app + bake into image"
```

---

## Task 2: WhatsApp Settings DocType

**Files:**
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/whatsapp_settings/__init__.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/whatsapp_settings/whatsapp_settings.json`
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/whatsapp_settings/whatsapp_settings.py`

- [ ] **Step 1: Create the DocType JSON**

`whatsapp_settings.json`:
```json
{
 "actions": [],
 "creation": "2026-05-21 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "issingle": 1,
 "field_order": [
  "section_api", "phone_number_id", "business_account_id", "access_token",
  "section_webhook", "webhook_verify_token", "app_secret",
  "section_send", "default_language", "rate_limit_per_second", "max_retries_5xx"
 ],
 "fields": [
  {"fieldname":"section_api","fieldtype":"Section Break","label":"Cloud API"},
  {"fieldname":"phone_number_id","label":"Phone Number ID","fieldtype":"Data","reqd":1},
  {"fieldname":"business_account_id","label":"Business Account ID","fieldtype":"Data","reqd":1},
  {"fieldname":"access_token","label":"Access Token","fieldtype":"Password","reqd":1},
  {"fieldname":"section_webhook","fieldtype":"Section Break","label":"Webhook"},
  {"fieldname":"webhook_verify_token","label":"Verify Token","fieldtype":"Password","reqd":1},
  {"fieldname":"app_secret","label":"App Secret","fieldtype":"Password","reqd":1},
  {"fieldname":"section_send","fieldtype":"Section Break","label":"Send"},
  {"fieldname":"default_language","label":"Default Language","fieldtype":"Data","default":"de"},
  {"fieldname":"rate_limit_per_second","label":"Rate Limit / Second","fieldtype":"Int","default":"80"},
  {"fieldname":"max_retries_5xx","label":"Max 5xx Retries","fieldtype":"Int","default":"3"}
 ],
 "modified": "2026-05-21 00:00:00",
 "module": "WhatsApp Broadcast",
 "name": "WhatsApp Settings",
 "owner": "Administrator",
 "permissions": [
  {"role":"System Manager","read":1,"write":1,"create":1}
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "track_changes": 1
}
```

`whatsapp_settings.py`:
```python
import frappe
from frappe.model.document import Document


class WhatsAppSettings(Document):
    pass


def get_settings() -> "WhatsAppSettings":
    return frappe.get_single("WhatsApp Settings")
```

Empty `__init__.py`.

- [ ] **Step 2: Migrate + verify in Desk**

```bash
make migrate
```
Open `http://localhost:8080/app/whatsapp-settings` as Administrator. Form loads with all fields.

- [ ] **Step 3: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): WhatsApp Settings single doctype"
```

---

## Task 3: WhatsApp Tag + Recipient DocTypes

**Files:**
- Create: `.../doctype/whatsapp_tag/whatsapp_tag.json`
- Create: `.../doctype/whatsapp_tag/whatsapp_tag.py`
- Create: `.../doctype/whatsapp_recipient_tag/whatsapp_recipient_tag.json`
- Create: `.../doctype/whatsapp_recipient_tag/whatsapp_recipient_tag.py`
- Create: `.../doctype/whatsapp_recipient/whatsapp_recipient.json`
- Create: `.../doctype/whatsapp_recipient/whatsapp_recipient.py`

(Plus `__init__.py` in each folder.)

- [ ] **Step 1: Create WhatsApp Tag**

`whatsapp_tag.json`:
```json
{
 "actions": [],
 "autoname": "field:tag_name",
 "creation": "2026-05-21 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": ["tag_name"],
 "fields": [
  {"fieldname":"tag_name","label":"Tag","fieldtype":"Data","reqd":1,"unique":1,"in_list_view":1}
 ],
 "modified": "2026-05-21 00:00:00",
 "module": "WhatsApp Broadcast",
 "name": "WhatsApp Tag",
 "owner": "Administrator",
 "permissions": [
  {"role":"System Manager","read":1,"write":1,"create":1,"delete":1},
  {"role":"WhatsApp Manager","read":1,"write":1,"create":1,"delete":1},
  {"role":"WhatsApp User","read":1}
 ],
 "sort_field": "modified","sort_order":"DESC"
}
```

`whatsapp_tag.py`:
```python
from frappe.model.document import Document
class WhatsAppTag(Document): pass
```

- [ ] **Step 2: Create WhatsApp Recipient Tag (child)**

`whatsapp_recipient_tag.json`:
```json
{
 "actions": [],
 "creation": "2026-05-21 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "istable": 1,
 "field_order": ["tag"],
 "fields": [
  {"fieldname":"tag","label":"Tag","fieldtype":"Link","options":"WhatsApp Tag","reqd":1,"in_list_view":1}
 ],
 "modified": "2026-05-21 00:00:00",
 "module": "WhatsApp Broadcast",
 "name": "WhatsApp Recipient Tag",
 "owner": "Administrator",
 "permissions": [],
 "sort_field":"modified","sort_order":"DESC"
}
```

`whatsapp_recipient_tag.py`:
```python
from frappe.model.document import Document
class WhatsAppRecipientTag(Document): pass
```

- [ ] **Step 3: Create WhatsApp Recipient**

`whatsapp_recipient.json`:
```json
{
 "actions": [],
 "autoname": "field:phone_number",
 "creation": "2026-05-21 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": ["recipient_name","phone_number","opt_in_status","opt_in_date","tags","notes"],
 "fields": [
  {"fieldname":"recipient_name","label":"Name","fieldtype":"Data","reqd":1,"in_list_view":1},
  {"fieldname":"phone_number","label":"Phone (E.164)","fieldtype":"Data","reqd":1,"unique":1,"in_list_view":1},
  {"fieldname":"opt_in_status","label":"Opt-in","fieldtype":"Select","options":"pending\nopted_in\nopted_out","default":"pending","in_list_view":1},
  {"fieldname":"opt_in_date","label":"Opt-in Date","fieldtype":"Datetime"},
  {"fieldname":"tags","label":"Tags","fieldtype":"Table MultiSelect","options":"WhatsApp Recipient Tag"},
  {"fieldname":"notes","label":"Notes","fieldtype":"Small Text"}
 ],
 "modified": "2026-05-21 00:00:00",
 "module": "WhatsApp Broadcast",
 "name": "WhatsApp Recipient",
 "owner": "Administrator",
 "permissions": [
  {"role":"System Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1},
  {"role":"WhatsApp Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1},
  {"role":"WhatsApp User","read":1,"report":1}
 ],
 "sort_field":"modified","sort_order":"DESC","track_changes":1
}
```

`whatsapp_recipient.py`:
```python
import re
import frappe
from frappe.model.document import Document

E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class WhatsAppRecipient(Document):
    def validate(self):
        if not E164.match(self.phone_number or ""):
            frappe.throw("phone_number must be E.164 format, e.g. +491701234567")
        if self.opt_in_status == "opted_in" and not self.opt_in_date:
            self.opt_in_date = frappe.utils.now_datetime()
```

- [ ] **Step 4: Migrate + smoke test**

```bash
make migrate
```
In Desk, create one Tag "vip", one Recipient with valid E.164 number + tag "vip". Try invalid number "123" — should throw.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): Tag + Recipient doctypes with E.164 validation"
```

---

## Task 4: `meta_client.py` — TDD

**Files:**
- Create: `whatsapp_broadcast/whatsapp_broadcast/api/__init__.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/api/meta_client.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/__init__.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_meta_client.py`

- [ ] **Step 1: Install test dependency**

Add to a dev shell inside backend container:
```bash
docker compose exec backend /home/frappe/frappe-bench/env/bin/pip install responses
```
(For permanent inclusion, also append `responses` to `whatsapp_broadcast/whatsapp_broadcast/requirements.txt`; Frappe installs requirements on image build.)

- [ ] **Step 2: Write failing tests**

`tests/test_meta_client.py`:
```python
import json
import responses
import pytest
from frappe.tests.utils import FrappeTestCase
import frappe
from whatsapp_broadcast.api import meta_client


def _set_settings():
    s = frappe.get_single("WhatsApp Settings")
    s.phone_number_id = "111"
    s.business_account_id = "222"
    s.access_token = "TOKEN"
    s.webhook_verify_token = "VT"
    s.app_secret = "SECRET"
    s.default_language = "de"
    s.rate_limit_per_second = 80
    s.max_retries_5xx = 3
    s.save(ignore_permissions=True)
    frappe.db.commit()


class TestMetaClient(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _set_settings()

    @responses.activate
    def test_send_template_success_returns_message_id(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.ABC"}]},
            status=200,
        )
        resp = meta_client.send_template(
            to="+491701234567",
            template_name="hello_world",
            lang="de",
            components=[],
        )
        self.assertEqual(resp["messages"][0]["id"], "wamid.ABC")
        body = json.loads(responses.calls[0].request.body)
        self.assertEqual(body["to"], "+491701234567")
        self.assertEqual(body["template"]["name"], "hello_world")
        self.assertEqual(
            responses.calls[0].request.headers["Authorization"], "Bearer TOKEN"
        )

    @responses.activate
    def test_send_template_4xx_raises_metaapierror_no_retry(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 132000, "message": "Template not approved"}},
            status=400,
        )
        with pytest.raises(meta_client.MetaAPIError) as exc:
            meta_client.send_template(
                to="+491701234567", template_name="x", lang="de", components=[]
            )
        self.assertEqual(exc.value.status_code, 400)
        self.assertEqual(exc.value.meta_code, 132000)
        self.assertFalse(exc.value.retryable)

    @responses.activate
    def test_send_template_5xx_marks_retryable(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 1, "message": "boom"}},
            status=503,
        )
        with pytest.raises(meta_client.MetaAPIError) as exc:
            meta_client.send_template(
                to="+491701234567", template_name="x", lang="de", components=[]
            )
        self.assertTrue(exc.value.retryable)

    @responses.activate
    def test_send_template_429_marks_retryable(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 80007, "message": "rate"}},
            status=429,
        )
        with pytest.raises(meta_client.MetaAPIError) as exc:
            meta_client.send_template(
                to="+491701234567", template_name="x", lang="de", components=[]
            )
        self.assertTrue(exc.value.retryable)

    @responses.activate
    def test_submit_template_posts_to_waba(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/222/message_templates",
            json={"id": "TPL_1", "status": "PENDING"},
            status=200,
        )
        resp = meta_client.submit_template(
            {"name": "hi", "language": "de", "category": "MARKETING", "components": []}
        )
        self.assertEqual(resp["id"], "TPL_1")
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_meta_client
```
Expected: ImportError / module not found on `meta_client`.

- [ ] **Step 4: Implement `meta_client.py`**

`whatsapp_broadcast/whatsapp_broadcast/api/__init__.py`: empty.

`whatsapp_broadcast/whatsapp_broadcast/api/meta_client.py`:
```python
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
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_meta_client
```
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): meta_client wrapper for Graph API with typed errors"
```

---

## Task 5: Token-bucket throttle — TDD

**Files:**
- Create: `whatsapp_broadcast/whatsapp_broadcast/tasks/__init__.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tasks/token_bucket.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_token_bucket.py`

- [ ] **Step 1: Write failing tests**

`tests/test_token_bucket.py`:
```python
import time
from frappe.tests.utils import FrappeTestCase
import frappe
from whatsapp_broadcast.tasks.token_bucket import TokenBucket


class TestTokenBucket(FrappeTestCase):
    def setUp(self):
        # use a unique key so tests don't interfere
        self.bucket = TokenBucket(key=f"test_bucket_{time.time()}", capacity=5, refill_per_sec=5)

    def test_first_n_acquires_within_capacity_dont_sleep(self):
        start = time.monotonic()
        for _ in range(5):
            self.bucket.acquire()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)

    def test_acquire_beyond_capacity_blocks_until_refill(self):
        for _ in range(5):
            self.bucket.acquire()
        start = time.monotonic()
        self.bucket.acquire()  # 6th must wait ~0.2s for 1 token
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 0.5)
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_token_bucket
```
Expected: ImportError.

- [ ] **Step 3: Implement**

`whatsapp_broadcast/whatsapp_broadcast/tasks/__init__.py`: empty.

`whatsapp_broadcast/whatsapp_broadcast/tasks/token_bucket.py`:
```python
from __future__ import annotations
import time
import frappe

LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local delta = math.max(0, now - ts)
tokens = math.min(capacity, tokens + delta * refill)
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
else
  wait = (1 - tokens) / refill
  tokens = 0
  now = now + wait
end
redis.call('HMSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, 60)
return tostring(wait)
"""


class TokenBucket:
    def __init__(self, key: str, capacity: int, refill_per_sec: float):
        self.key = f"wa_bucket:{key}"
        self.capacity = capacity
        self.refill = refill_per_sec
        self._client = frappe.cache().redis
        self._script = self._client.register_script(LUA)

    def acquire(self) -> None:
        wait_s = float(
            self._script(keys=[self.key], args=[self.capacity, self.refill, time.time()])
        )
        if wait_s > 0:
            time.sleep(wait_s)
```

- [ ] **Step 4: Run tests pass**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_token_bucket
```
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): Redis Lua-backed token-bucket throttle"
```

---

## Task 6: Template + Template Button DocTypes (no actions yet)

**Files:**
- Create: `.../doctype/whatsapp_template_button/whatsapp_template_button.{json,py}` (+ `__init__.py`)
- Create: `.../doctype/whatsapp_template/whatsapp_template.{json,py}` (+ `__init__.py`)
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_template_validation.py`

- [ ] **Step 1: Write failing validation tests**

`tests/test_template_validation.py`:
```python
import frappe
from frappe.tests.utils import FrappeTestCase


def _make(template_name="t1", body="Hello {{1}} and {{2}}", header_type="none", footer=None, buttons=None):
    doc = frappe.get_doc({
        "doctype": "WhatsApp Template",
        "template_name": template_name,
        "language": "de",
        "category": "MARKETING",
        "header_type": header_type,
        "body_text": body,
        "footer_text": footer or "",
        "buttons": buttons or [],
    })
    return doc


class TestTemplateValidation(FrappeTestCase):
    def test_variable_count_computed_from_body(self):
        doc = _make(body="Hi {{1}}, your order {{2}} ships {{3}}.")
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.variable_count, 3)
        doc.delete()

    def test_body_over_1024_chars_throws(self):
        doc = _make(template_name="too_long", body="x" * 1025)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_footer_over_60_chars_throws(self):
        doc = _make(template_name="bad_footer", footer="y" * 61)
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_invalid_template_name_throws(self):
        doc = _make(template_name="Bad-Name")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_new_template_defaults_to_local_status(self):
        doc = _make(template_name="status_default")
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.meta_status, "local")
        doc.delete()
```

- [ ] **Step 2: Run to confirm DocType-not-found failures**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_template_validation
```
Expected: errors about missing DocType.

- [ ] **Step 3: Implement Template Button**

`whatsapp_template_button.json`:
```json
{
 "actions": [],
 "creation": "2026-05-21 00:00:00",
 "doctype": "DocType","engine":"InnoDB","istable":1,
 "field_order":["button_type","text","url_or_phone"],
 "fields":[
  {"fieldname":"button_type","label":"Type","fieldtype":"Select","options":"quick_reply\nurl\nphone","reqd":1,"in_list_view":1},
  {"fieldname":"text","label":"Text","fieldtype":"Data","reqd":1,"in_list_view":1},
  {"fieldname":"url_or_phone","label":"URL / Phone","fieldtype":"Data","in_list_view":1}
 ],
 "modified":"2026-05-21 00:00:00","module":"WhatsApp Broadcast","name":"WhatsApp Template Button",
 "owner":"Administrator","permissions":[],"sort_field":"modified","sort_order":"DESC"
}
```

`whatsapp_template_button.py`:
```python
from frappe.model.document import Document
class WhatsAppTemplateButton(Document): pass
```

- [ ] **Step 4: Implement Template**

`whatsapp_template.json`:
```json
{
 "actions": [],
 "autoname":"field:template_name",
 "creation": "2026-05-21 00:00:00",
 "doctype":"DocType","engine":"InnoDB",
 "field_order":[
  "template_name","language","category","col_meta","meta_status","meta_template_id","rejection_reason",
  "sec_header","header_type","header_content",
  "sec_body","body_text","variable_count",
  "sec_footer","footer_text",
  "sec_buttons","buttons"
 ],
 "fields":[
  {"fieldname":"template_name","label":"Template Name","fieldtype":"Data","reqd":1,"unique":1,"in_list_view":1},
  {"fieldname":"language","label":"Language","fieldtype":"Data","reqd":1,"default":"de","in_list_view":1},
  {"fieldname":"category","label":"Category","fieldtype":"Select","options":"MARKETING\nUTILITY\nAUTHENTICATION","reqd":1,"in_list_view":1},
  {"fieldname":"col_meta","fieldtype":"Column Break"},
  {"fieldname":"meta_status","label":"Meta Status","fieldtype":"Select","options":"local\npending\napproved\nrejected\npaused","default":"local","in_list_view":1,"read_only":1},
  {"fieldname":"meta_template_id","label":"Meta Template ID","fieldtype":"Data","read_only":1},
  {"fieldname":"rejection_reason","label":"Rejection Reason","fieldtype":"Small Text","read_only":1},
  {"fieldname":"sec_header","fieldtype":"Section Break","label":"Header"},
  {"fieldname":"header_type","label":"Header Type","fieldtype":"Select","options":"none\ntext\nimage\nvideo\ndocument","default":"none"},
  {"fieldname":"header_content","label":"Header Text","fieldtype":"Small Text","depends_on":"eval:doc.header_type=='text'"},
  {"fieldname":"sec_body","fieldtype":"Section Break","label":"Body"},
  {"fieldname":"body_text","label":"Body Text","fieldtype":"Text","reqd":1,"description":"Max 1024 chars. Use {{1}}, {{2}} for variables. *bold*, _italic_, ~strike~, ```mono```."},
  {"fieldname":"variable_count","label":"Variable Count","fieldtype":"Int","read_only":1},
  {"fieldname":"sec_footer","fieldtype":"Section Break","label":"Footer"},
  {"fieldname":"footer_text","label":"Footer Text","fieldtype":"Data"},
  {"fieldname":"sec_buttons","fieldtype":"Section Break","label":"Buttons"},
  {"fieldname":"buttons","label":"Buttons","fieldtype":"Table","options":"WhatsApp Template Button"}
 ],
 "modified":"2026-05-21 00:00:00","module":"WhatsApp Broadcast","name":"WhatsApp Template","owner":"Administrator",
 "permissions":[
  {"role":"System Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1,"submit":0},
  {"role":"WhatsApp Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1},
  {"role":"WhatsApp User","read":1}
 ],
 "sort_field":"modified","sort_order":"DESC","track_changes":1
}
```

`whatsapp_template.py`:
```python
import re
import frappe
from frappe.model.document import Document

NAME_RE = re.compile(r"^[a-z0-9_]+$")
VAR_RE = re.compile(r"\{\{(\d+)\}\}")


class WhatsAppTemplate(Document):
    def validate(self):
        if not NAME_RE.match(self.template_name or ""):
            frappe.throw("template_name must match [a-z0-9_]+ (Meta requirement)")
        if len(self.body_text or "") > 1024:
            frappe.throw("body_text must be <= 1024 chars")
        if self.footer_text and len(self.footer_text) > 60:
            frappe.throw("footer_text must be <= 60 chars")
        if self.header_type == "text" and self.header_content and len(self.header_content) > 60:
            frappe.throw("header text must be <= 60 chars")
        self.variable_count = self._compute_variable_count()

    def _compute_variable_count(self) -> int:
        nums = {int(m) for m in VAR_RE.findall(self.body_text or "")}
        return max(nums) if nums else 0
```

- [ ] **Step 5: Migrate + run tests**

```bash
make migrate
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_template_validation
```
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): Template doctype with validation + variable count"
```

---

## Task 7: Template Meta actions (Submit + Sync)

**Files:**
- Modify: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/whatsapp_template/whatsapp_template.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/doctype/whatsapp_template/whatsapp_template.js`
- Modify: `whatsapp_broadcast/whatsapp_broadcast/tests/test_template_validation.py` (append tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_template_validation.py`:
```python
import responses
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_template.whatsapp_template import (
    submit_to_meta, sync_status,
)


class TestTemplateActions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        s = frappe.get_single("WhatsApp Settings")
        s.phone_number_id = "111"; s.business_account_id = "222"
        s.access_token = "TOKEN"; s.webhook_verify_token = "VT"; s.app_secret = "SECRET"
        s.save(ignore_permissions=True); frappe.db.commit()

    @responses.activate
    def test_submit_to_meta_sets_pending_and_id(self):
        doc = _make(template_name="action_submit").insert(ignore_permissions=True)
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/222/message_templates",
            json={"id": "TPL_X", "status": "PENDING"}, status=200,
        )
        submit_to_meta(doc.name)
        doc.reload()
        self.assertEqual(doc.meta_status, "pending")
        self.assertEqual(doc.meta_template_id, "TPL_X")

    @responses.activate
    def test_sync_status_updates_approved(self):
        doc = _make(template_name="action_sync").insert(ignore_permissions=True)
        doc.db_set("meta_template_id", "TPL_Y")
        responses.add(
            responses.GET,
            "https://graph.facebook.com/v20.0/222/message_templates",
            json={"data": [{"name": "action_sync", "language": "de", "status": "APPROVED", "id": "TPL_Y"}]},
            status=200,
        )
        sync_status(doc.name)
        doc.reload()
        self.assertEqual(doc.meta_status, "approved")
```

- [ ] **Step 2: Run to confirm failure**

Same `bench --site frontend run-tests` command as before. Expected: import error / function not found.

- [ ] **Step 3: Implement actions**

Append to `whatsapp_template.py`:
```python
from whatsapp_broadcast.api import meta_client


def _build_components(doc: "WhatsAppTemplate") -> list[dict]:
    comps = []
    if doc.header_type == "text" and doc.header_content:
        comps.append({"type": "HEADER", "format": "TEXT", "text": doc.header_content})
    elif doc.header_type in ("image", "video", "document"):
        comps.append({"type": "HEADER", "format": doc.header_type.upper()})
    comps.append({"type": "BODY", "text": doc.body_text})
    if doc.footer_text:
        comps.append({"type": "FOOTER", "text": doc.footer_text})
    if doc.buttons:
        comps.append({
            "type": "BUTTONS",
            "buttons": [_button_payload(b) for b in doc.buttons],
        })
    return comps


def _button_payload(b) -> dict:
    if b.button_type == "quick_reply":
        return {"type": "QUICK_REPLY", "text": b.text}
    if b.button_type == "url":
        return {"type": "URL", "text": b.text, "url": b.url_or_phone}
    return {"type": "PHONE_NUMBER", "text": b.text, "phone_number": b.url_or_phone}


@frappe.whitelist()
def submit_to_meta(name: str) -> None:
    doc = frappe.get_doc("WhatsApp Template", name)
    payload = {
        "name": doc.template_name,
        "language": doc.language,
        "category": doc.category,
        "components": _build_components(doc),
    }
    resp = meta_client.submit_template(payload)
    doc.db_set("meta_template_id", resp.get("id"))
    doc.db_set("meta_status", "pending")


@frappe.whitelist()
def sync_status(name: str) -> None:
    doc = frappe.get_doc("WhatsApp Template", name)
    info = meta_client.get_template_status(doc.template_name, doc.language)
    status = (info.get("status") or "").lower()
    if status in ("local", "pending", "approved", "rejected", "paused"):
        doc.db_set("meta_status", status)
    if status == "rejected":
        doc.db_set("rejection_reason", info.get("rejected_reason", ""))
```

- [ ] **Step 4: Add Desk buttons**

Create `whatsapp_template.js`:
```javascript
frappe.ui.form.on('WhatsApp Template', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Submit to Meta'), () => {
                frappe.call({
                    method: 'whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_template.whatsapp_template.submit_to_meta',
                    args: { name: frm.doc.name },
                    callback: () => { frappe.show_alert({message: 'Submitted', indicator: 'green'}); frm.reload_doc(); },
                });
            });
            frm.add_custom_button(__('Sync Status'), () => {
                frappe.call({
                    method: 'whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_template.whatsapp_template.sync_status',
                    args: { name: frm.doc.name },
                    callback: () => { frm.reload_doc(); },
                });
            });
        }
    },
});
```

- [ ] **Step 5: Run tests pass**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_template_validation
```
Expected: 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): template Submit/Sync Meta actions + desk buttons"
```

---

## Task 8: Webhook endpoint — TDD

**Files:**
- Create: `whatsapp_broadcast/whatsapp_broadcast/api/webhook.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_webhook.py`

(Webhook updates `WhatsApp Message Log` which is created in Task 10. To keep tests independent, we test signature + verify-challenge here; status-update tests live in Task 10's suite.)

- [ ] **Step 1: Write failing tests**

`tests/test_webhook.py`:
```python
import hmac, hashlib, json
import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.api import webhook


class TestWebhookSignature(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        s = frappe.get_single("WhatsApp Settings")
        s.phone_number_id = "111"; s.business_account_id = "222"
        s.access_token = "TOKEN"; s.webhook_verify_token = "VT"; s.app_secret = "SECRET"
        s.save(ignore_permissions=True); frappe.db.commit()

    def test_verify_challenge_returns_challenge(self):
        result = webhook._verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "VT", "hub.challenge": "C123"})
        self.assertEqual(result, "C123")

    def test_verify_challenge_wrong_token_raises(self):
        with self.assertRaises(frappe.PermissionError):
            webhook._verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "C"})

    def test_verify_signature_valid(self):
        body = b'{"x":1}'
        sig = "sha256=" + hmac.new(b"SECRET", body, hashlib.sha256).hexdigest()
        self.assertTrue(webhook._verify_signature(body, sig))

    def test_verify_signature_invalid(self):
        self.assertFalse(webhook._verify_signature(b'{"x":1}', "sha256=deadbeef"))

    def test_verify_signature_missing(self):
        self.assertFalse(webhook._verify_signature(b'{}', None))
```

- [ ] **Step 2: Run, confirm failure**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_webhook
```
Expected: ImportError.

- [ ] **Step 3: Implement webhook**

`whatsapp_broadcast/whatsapp_broadcast/api/webhook.py`:
```python
from __future__ import annotations
import hmac, hashlib, json
import frappe


def _settings():
    return frappe.get_single("WhatsApp Settings")


def _verify_challenge(query: dict) -> str:
    expected = _settings().get_password("webhook_verify_token")
    if query.get("hub.mode") == "subscribe" and query.get("hub.verify_token") == expected:
        return query.get("hub.challenge", "")
    raise frappe.PermissionError("verify token mismatch")


def _verify_signature(raw_body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    secret = _settings().get_password("app_secret").encode()
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def handle() -> str | dict:
    req = frappe.request
    if req.method == "GET":
        return _verify_challenge(req.args.to_dict())

    raw = req.get_data() or b""
    sig = req.headers.get("X-Hub-Signature-256")
    if not _verify_signature(raw, sig):
        frappe.local.response.http_status_code = 403
        frappe.logger().warning("whatsapp webhook: bad signature")
        return {"ok": False}

    payload = json.loads(raw.decode() or "{}")
    _process(payload)
    return {"ok": True}


def _process(payload: dict) -> None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            for status in value.get("statuses", []) or []:
                _apply_status(status)


def _apply_status(status: dict) -> None:
    mid = status.get("id")
    if not mid:
        return
    log_name = frappe.db.get_value("WhatsApp Message Log", {"meta_message_id": mid}, "name")
    if not log_name:
        return
    log = frappe.get_doc("WhatsApp Message Log", log_name)
    new_status = (status.get("status") or "").lower()
    ts = frappe.utils.get_datetime_str(frappe.utils.get_datetime(int(status.get("timestamp", "0"))))
    if new_status == "sent":
        log.db_set({"status": "sent", "sent_at": ts})
    elif new_status == "delivered":
        log.db_set({"status": "delivered", "delivered_at": ts})
        _bump_counter(log.post, "delivered_count")
    elif new_status == "read":
        log.db_set({"status": "read", "read_at": ts})
        _bump_counter(log.post, "read_count")
    elif new_status == "failed":
        err = (status.get("errors") or [{}])[0]
        log.db_set({"status": "failed", "error_code": str(err.get("code", "")), "error_message": err.get("message", "")})
        _bump_counter(log.post, "failed_count")
    log.db_set("raw_webhook_payload", json.dumps(status))


def _bump_counter(post_name: str, field: str) -> None:
    frappe.db.sql(
        f"UPDATE `tabWhatsApp Post` SET `{field}` = COALESCE(`{field}`, 0) + 1 WHERE name = %s",
        (post_name,),
    )
```

- [ ] **Step 4: Run tests pass**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_webhook
```
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): webhook handler with HMAC verification + status routing"
```

---

## Task 9: WhatsApp Post + child DocTypes (without send)

**Files:**
- Create: `.../doctype/whatsapp_post_tag/whatsapp_post_tag.{json,py}` (+ `__init__.py`)
- Create: `.../doctype/whatsapp_post_recipient/whatsapp_post_recipient.{json,py}` (+ `__init__.py`)
- Create: `.../doctype/whatsapp_post/whatsapp_post.{json,py}` (+ `__init__.py`)
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_recipient_expansion.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_post_validation.py`

- [ ] **Step 1: Write failing tests**

`tests/test_recipient_expansion.py`:
```python
import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import expand_recipients


def _recipient(phone, name, tags=None, opted=True):
    if frappe.db.exists("WhatsApp Recipient", phone):
        frappe.delete_doc("WhatsApp Recipient", phone, force=True)
    return frappe.get_doc({
        "doctype": "WhatsApp Recipient",
        "recipient_name": name, "phone_number": phone,
        "opt_in_status": "opted_in" if opted else "opted_out",
        "tags": [{"tag": t} for t in (tags or [])],
    }).insert(ignore_permissions=True)


def _tag(name):
    if not frappe.db.exists("WhatsApp Tag", name):
        frappe.get_doc({"doctype": "WhatsApp Tag", "tag_name": name}).insert(ignore_permissions=True)


class TestRecipientExpansion(FrappeTestCase):
    def setUp(self):
        _tag("vip"); _tag("beta")
        _recipient("+491700000001", "A", ["vip"])
        _recipient("+491700000002", "B", ["vip", "beta"])
        _recipient("+491700000003", "C", ["beta"])
        _recipient("+491700000004", "D", ["vip"], opted=False)

    def test_by_tags_returns_opted_in_dedup(self):
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "p1",
            "template": _ensure_template(), "variable_values": "{}",
            "recipient_mode": "by_tags",
            "recipient_tags": [{"tag": "vip"}, {"tag": "beta"}],
        }).insert(ignore_permissions=True)
        targets, skipped = expand_recipients(post.name)
        phones = sorted(r.phone_number for r in targets)
        self.assertEqual(phones, ["+491700000001", "+491700000002", "+491700000003"])
        self.assertEqual(skipped, 1)

    def test_explicit_list_filters_opted_out(self):
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "p2",
            "template": _ensure_template(), "variable_values": "{}",
            "recipient_mode": "explicit_list",
            "explicit_recipients": [
                {"recipient": "+491700000001"},
                {"recipient": "+491700000004"},
            ],
        }).insert(ignore_permissions=True)
        targets, skipped = expand_recipients(post.name)
        self.assertEqual([r.phone_number for r in targets], ["+491700000001"])
        self.assertEqual(skipped, 1)


def _ensure_template():
    name = "expansion_tpl"
    if not frappe.db.exists("WhatsApp Template", name):
        frappe.get_doc({
            "doctype": "WhatsApp Template", "template_name": name,
            "language": "de", "category": "MARKETING",
            "header_type": "none", "body_text": "Hi", "meta_status": "approved",
        }).insert(ignore_permissions=True)
    return name
```

`tests/test_post_validation.py`:
```python
import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import validate_for_send


def _tpl(name, body, meta_status="approved", header_type="none"):
    if frappe.db.exists("WhatsApp Template", name):
        return name
    frappe.get_doc({
        "doctype": "WhatsApp Template", "template_name": name,
        "language": "de", "category": "MARKETING",
        "header_type": header_type, "body_text": body,
        "meta_status": meta_status,
    }).insert(ignore_permissions=True)
    return name


class TestPostValidation(FrappeTestCase):
    def test_send_blocked_when_template_not_approved(self):
        tpl = _tpl("pending_tpl", "Hi {{1}}", meta_status="pending")
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "x", "template": tpl,
            "variable_values": '{"1":"A"}', "recipient_mode": "explicit_list",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            validate_for_send(post)

    def test_send_blocked_when_variables_missing(self):
        tpl = _tpl("vars_tpl", "Hi {{1}} {{2}}")
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "y", "template": tpl,
            "variable_values": '{"1":"A"}', "recipient_mode": "explicit_list",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            validate_for_send(post)

    def test_send_blocked_when_media_header_without_attachment(self):
        tpl = _tpl("img_tpl", "Hi", header_type="image")
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "z", "template": tpl,
            "variable_values": "{}", "recipient_mode": "explicit_list",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            validate_for_send(post)
```

- [ ] **Step 2: Run, confirm failures**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_recipient_expansion
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_post_validation
```
Expected: errors about missing DocTypes / functions.

- [ ] **Step 3: Implement Post Tag child**

`whatsapp_post_tag.json`:
```json
{
 "actions":[], "creation":"2026-05-21 00:00:00", "doctype":"DocType","engine":"InnoDB","istable":1,
 "field_order":["tag"],
 "fields":[{"fieldname":"tag","label":"Tag","fieldtype":"Link","options":"WhatsApp Tag","reqd":1,"in_list_view":1}],
 "modified":"2026-05-21 00:00:00","module":"WhatsApp Broadcast","name":"WhatsApp Post Tag",
 "owner":"Administrator","permissions":[],"sort_field":"modified","sort_order":"DESC"
}
```
`whatsapp_post_tag.py`:
```python
from frappe.model.document import Document
class WhatsAppPostTag(Document): pass
```

- [ ] **Step 4: Implement Post Recipient child**

`whatsapp_post_recipient.json`:
```json
{
 "actions":[], "creation":"2026-05-21 00:00:00", "doctype":"DocType","engine":"InnoDB","istable":1,
 "field_order":["recipient"],
 "fields":[{"fieldname":"recipient","label":"Recipient","fieldtype":"Link","options":"WhatsApp Recipient","reqd":1,"in_list_view":1}],
 "modified":"2026-05-21 00:00:00","module":"WhatsApp Broadcast","name":"WhatsApp Post Recipient",
 "owner":"Administrator","permissions":[],"sort_field":"modified","sort_order":"DESC"
}
```
`whatsapp_post_recipient.py`:
```python
from frappe.model.document import Document
class WhatsAppPostRecipient(Document): pass
```

- [ ] **Step 5: Implement Post**

`whatsapp_post.json`:
```json
{
 "actions":[], "autoname":"WP-.YYYY.-.#####",
 "creation":"2026-05-21 00:00:00","doctype":"DocType","engine":"InnoDB",
 "field_order":[
  "title","template","status","col_meta","created_by","queued_at","completed_at",
  "sec_vars","variable_values","media_attachment","media_id_cache",
  "sec_recipients","recipient_mode","recipient_tags","explicit_recipients",
  "sec_counters","total_recipients","sent_count","delivered_count","read_count","failed_count","skipped_opt_out_count"
 ],
 "fields":[
  {"fieldname":"title","label":"Title","fieldtype":"Data","reqd":1,"in_list_view":1},
  {"fieldname":"template","label":"Template","fieldtype":"Link","options":"WhatsApp Template","reqd":1,"in_list_view":1},
  {"fieldname":"status","label":"Status","fieldtype":"Select","options":"draft\nqueued\nsending\ncompleted\nfailed","default":"draft","read_only":1,"in_list_view":1},
  {"fieldname":"col_meta","fieldtype":"Column Break"},
  {"fieldname":"created_by","label":"Created By","fieldtype":"Link","options":"User","read_only":1},
  {"fieldname":"queued_at","label":"Queued At","fieldtype":"Datetime","read_only":1},
  {"fieldname":"completed_at","label":"Completed At","fieldtype":"Datetime","read_only":1},
  {"fieldname":"sec_vars","fieldtype":"Section Break","label":"Variables & Media"},
  {"fieldname":"variable_values","label":"Variable Values (JSON)","fieldtype":"JSON","default":"{}"},
  {"fieldname":"media_attachment","label":"Media Attachment","fieldtype":"Attach"},
  {"fieldname":"media_id_cache","label":"Meta Media ID","fieldtype":"Data","read_only":1},
  {"fieldname":"sec_recipients","fieldtype":"Section Break","label":"Recipients"},
  {"fieldname":"recipient_mode","label":"Mode","fieldtype":"Select","options":"by_tags\nexplicit_list","default":"by_tags","reqd":1},
  {"fieldname":"recipient_tags","label":"Tags","fieldtype":"Table","options":"WhatsApp Post Tag","depends_on":"eval:doc.recipient_mode=='by_tags'"},
  {"fieldname":"explicit_recipients","label":"Explicit Recipients","fieldtype":"Table","options":"WhatsApp Post Recipient","depends_on":"eval:doc.recipient_mode=='explicit_list'"},
  {"fieldname":"sec_counters","fieldtype":"Section Break","label":"Counters"},
  {"fieldname":"total_recipients","label":"Total","fieldtype":"Int","read_only":1},
  {"fieldname":"sent_count","label":"Sent","fieldtype":"Int","read_only":1},
  {"fieldname":"delivered_count","label":"Delivered","fieldtype":"Int","read_only":1},
  {"fieldname":"read_count","label":"Read","fieldtype":"Int","read_only":1},
  {"fieldname":"failed_count","label":"Failed","fieldtype":"Int","read_only":1},
  {"fieldname":"skipped_opt_out_count","label":"Skipped (opt-out)","fieldtype":"Int","read_only":1}
 ],
 "modified":"2026-05-21 00:00:00","module":"WhatsApp Broadcast","name":"WhatsApp Post","owner":"Administrator",
 "permissions":[
  {"role":"System Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1},
  {"role":"WhatsApp Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1},
  {"role":"WhatsApp User","read":1,"report":1}
 ],
 "sort_field":"modified","sort_order":"DESC","track_changes":1
}
```

`whatsapp_post.py`:
```python
from __future__ import annotations
import json, re
import frappe
from frappe.model.document import Document

VAR_RE = re.compile(r"\{\{(\d+)\}\}")


class WhatsAppPost(Document):
    def before_insert(self):
        if not self.created_by:
            self.created_by = frappe.session.user

    def validate(self):
        # variable_values must be valid JSON
        try:
            json.loads(self.variable_values or "{}")
        except ValueError:
            frappe.throw("variable_values must be valid JSON")


def validate_for_send(post: WhatsAppPost) -> None:
    tpl = frappe.get_doc("WhatsApp Template", post.template)
    if tpl.meta_status != "approved":
        frappe.throw(f"Template {tpl.name} not approved (status={tpl.meta_status})")
    needed = {int(m) for m in VAR_RE.findall(tpl.body_text or "")}
    provided = {int(k) for k in json.loads(post.variable_values or "{}").keys()}
    if needed - provided:
        frappe.throw(f"Missing variable values: {sorted(needed - provided)}")
    if tpl.header_type in ("image", "video", "document") and not post.media_attachment:
        frappe.throw(f"Template header type {tpl.header_type} requires media_attachment")


def expand_recipients(post_name: str) -> tuple[list, int]:
    """Return (opted_in_recipient_docs, skipped_opt_out_count)."""
    post = frappe.get_doc("WhatsApp Post", post_name)
    candidate_names: set[str] = set()
    if post.recipient_mode == "by_tags":
        tags = [t.tag for t in (post.recipient_tags or [])]
        if tags:
            rows = frappe.db.sql(
                """SELECT DISTINCT r.name
                     FROM `tabWhatsApp Recipient` r
                     JOIN `tabWhatsApp Recipient Tag` rt ON rt.parent = r.name
                    WHERE rt.tag IN %(tags)s""",
                {"tags": tuple(tags)},
                as_dict=True,
            )
            candidate_names = {row.name for row in rows}
    else:
        candidate_names = {r.recipient for r in (post.explicit_recipients or [])}

    docs = [frappe.get_doc("WhatsApp Recipient", n) for n in candidate_names]
    opted = [d for d in docs if d.opt_in_status == "opted_in"]
    skipped = len(docs) - len(opted)
    return opted, skipped
```

- [ ] **Step 6: Migrate + run tests**

```bash
make migrate
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_recipient_expansion
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_post_validation
```
Expected: 2 + 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): Post doctype + recipient expansion + send-time validation"
```

---

## Task 10: Message Log DocType + sender RQ jobs — TDD

**Files:**
- Create: `.../doctype/whatsapp_message_log/whatsapp_message_log.{json,py}` (+ `__init__.py`)
- Create: `whatsapp_broadcast/whatsapp_broadcast/tasks/sender.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/tests/test_send_integration.py`

- [ ] **Step 1: Create Message Log DocType**

`whatsapp_message_log.json`:
```json
{
 "actions":[],"autoname":"WML-.YYYY.-.######",
 "creation":"2026-05-21 00:00:00","doctype":"DocType","engine":"InnoDB",
 "field_order":[
  "post","recipient","phone_number","status","col_meta","meta_message_id","retry_count",
  "sec_ts","sent_at","delivered_at","read_at",
  "sec_err","error_code","error_message","raw_webhook_payload"
 ],
 "fields":[
  {"fieldname":"post","label":"Post","fieldtype":"Link","options":"WhatsApp Post","reqd":1,"in_list_view":1},
  {"fieldname":"recipient","label":"Recipient","fieldtype":"Link","options":"WhatsApp Recipient","reqd":1,"in_list_view":1},
  {"fieldname":"phone_number","label":"Phone","fieldtype":"Data","in_list_view":1},
  {"fieldname":"status","label":"Status","fieldtype":"Select","options":"queued\nsent\ndelivered\nread\nfailed","default":"queued","in_list_view":1},
  {"fieldname":"col_meta","fieldtype":"Column Break"},
  {"fieldname":"meta_message_id","label":"Meta Message ID","fieldtype":"Data"},
  {"fieldname":"retry_count","label":"Retries","fieldtype":"Int","default":"0"},
  {"fieldname":"sec_ts","fieldtype":"Section Break","label":"Timestamps"},
  {"fieldname":"sent_at","label":"Sent","fieldtype":"Datetime"},
  {"fieldname":"delivered_at","label":"Delivered","fieldtype":"Datetime"},
  {"fieldname":"read_at","label":"Read","fieldtype":"Datetime"},
  {"fieldname":"sec_err","fieldtype":"Section Break","label":"Error / Audit"},
  {"fieldname":"error_code","label":"Error Code","fieldtype":"Data"},
  {"fieldname":"error_message","label":"Error Message","fieldtype":"Small Text"},
  {"fieldname":"raw_webhook_payload","label":"Last Webhook Payload","fieldtype":"JSON"}
 ],
 "modified":"2026-05-21 00:00:00","module":"WhatsApp Broadcast","name":"WhatsApp Message Log","owner":"Administrator",
 "permissions":[
  {"role":"System Manager","read":1,"write":1,"create":1,"delete":1,"export":1,"report":1},
  {"role":"WhatsApp Manager","read":1,"export":1,"report":1},
  {"role":"WhatsApp User","read":1,"report":1}
 ],
 "sort_field":"modified","sort_order":"DESC"
}
```

Add index on `meta_message_id` after migrate:
```python
# in whatsapp_message_log.py
import frappe
from frappe.model.document import Document


class WhatsAppMessageLog(Document):
    pass


def on_doctype_update():
    frappe.db.add_index("WhatsApp Message Log", ["meta_message_id"])
```

```bash
make migrate
```

- [ ] **Step 2: Write failing integration test**

`tests/test_send_integration.py`:
```python
import json, responses
import frappe
from frappe.tests.utils import FrappeTestCase
from whatsapp_broadcast.tasks import sender


def _settings():
    s = frappe.get_single("WhatsApp Settings")
    s.phone_number_id = "111"; s.business_account_id = "222"
    s.access_token = "TOKEN"; s.webhook_verify_token = "VT"; s.app_secret = "SECRET"
    s.rate_limit_per_second = 1000; s.max_retries_5xx = 1
    s.save(ignore_permissions=True); frappe.db.commit()


def _seed():
    if not frappe.db.exists("WhatsApp Tag", "send"):
        frappe.get_doc({"doctype": "WhatsApp Tag", "tag_name": "send"}).insert(ignore_permissions=True)
    for phone, name in [("+491701111101", "S1"), ("+491701111102", "S2")]:
        if frappe.db.exists("WhatsApp Recipient", phone):
            frappe.delete_doc("WhatsApp Recipient", phone, force=True)
        frappe.get_doc({
            "doctype": "WhatsApp Recipient",
            "recipient_name": name, "phone_number": phone, "opt_in_status": "opted_in",
            "tags": [{"tag": "send"}],
        }).insert(ignore_permissions=True)
    if not frappe.db.exists("WhatsApp Template", "send_tpl"):
        frappe.get_doc({
            "doctype": "WhatsApp Template", "template_name": "send_tpl",
            "language": "de", "category": "MARKETING",
            "header_type": "none", "body_text": "Hi {{1}}", "meta_status": "approved",
        }).insert(ignore_permissions=True)


class TestSendIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _settings(); _seed()

    @responses.activate
    def test_full_send_creates_logs_and_updates_counters(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.S1"}]}, status=200,
        )
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.S2"}]}, status=200,
        )
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "send_t1", "template": "send_tpl",
            "variable_values": '{"1":"Hans"}',
            "recipient_mode": "by_tags", "recipient_tags": [{"tag": "send"}],
        }).insert(ignore_permissions=True)
        sender.send_post(post.name, _inline=True)
        post.reload()
        self.assertEqual(post.status, "completed")
        self.assertEqual(post.total_recipients, 2)
        self.assertEqual(post.sent_count, 2)
        self.assertEqual(post.failed_count, 0)
        logs = frappe.get_all(
            "WhatsApp Message Log", filters={"post": post.name},
            fields=["meta_message_id", "status"],
        )
        ids = sorted(l.meta_message_id for l in logs)
        self.assertEqual(ids, ["wamid.S1", "wamid.S2"])
        self.assertTrue(all(l.status == "sent" for l in logs))

    @responses.activate
    def test_4xx_marks_failed_no_retry(self):
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"error": {"code": 132000, "message": "Bad"}}, status=400,
        )
        responses.add(
            responses.POST,
            "https://graph.facebook.com/v20.0/111/messages",
            json={"messages": [{"id": "wamid.OK"}]}, status=200,
        )
        post = frappe.get_doc({
            "doctype": "WhatsApp Post", "title": "send_t2", "template": "send_tpl",
            "variable_values": '{"1":"Hans"}',
            "recipient_mode": "by_tags", "recipient_tags": [{"tag": "send"}],
        }).insert(ignore_permissions=True)
        sender.send_post(post.name, _inline=True)
        post.reload()
        self.assertEqual(post.sent_count + post.failed_count, 2)
        self.assertEqual(post.failed_count, 1)
        self.assertEqual(post.status, "completed")
```

- [ ] **Step 3: Run, confirm failure**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_send_integration
```
Expected: `sender` module missing.

- [ ] **Step 4: Implement sender**

`whatsapp_broadcast/whatsapp_broadcast/tasks/sender.py`:
```python
from __future__ import annotations
import json, time
import frappe
from whatsapp_broadcast.api import meta_client
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import (
    expand_recipients, validate_for_send,
)
from whatsapp_broadcast.tasks.token_bucket import TokenBucket


def _bucket(rate: int) -> TokenBucket:
    return TokenBucket(key="global", capacity=rate, refill_per_sec=rate)


def _build_components(tpl, post, recipient) -> list[dict]:
    comps = []
    vars_ = json.loads(post.variable_values or "{}")
    if tpl.header_type in ("image", "video", "document"):
        media_id = post.media_id_cache
        link_field = {"image": "image", "video": "video", "document": "document"}[tpl.header_type]
        comps.append({
            "type": "header",
            "parameters": [{"type": tpl.header_type, tpl.header_type: {"id": media_id}}],
        })
    body_params = [{"type": "text", "text": vars_[str(i)]} for i in range(1, tpl.variable_count + 1)]
    if body_params:
        comps.append({"type": "body", "parameters": body_params})
    return comps


def _publish_progress(post_name: str) -> None:
    frappe.publish_realtime("whatsapp_post_progress", {"post": post_name}, after_commit=True)


def send_post(post_name: str, _inline: bool = False) -> None:
    post = frappe.get_doc("WhatsApp Post", post_name)
    validate_for_send(post)

    tpl = frappe.get_doc("WhatsApp Template", post.template)
    if tpl.header_type in ("image", "video", "document") and not post.media_id_cache:
        full = frappe.get_doc("File", {"file_url": post.media_attachment}).get_full_path()
        mime = {"image": "image/jpeg", "video": "video/mp4", "document": "application/pdf"}[tpl.header_type]
        post.db_set("media_id_cache", meta_client.upload_media(full, mime))

    targets, skipped = expand_recipients(post_name)
    post.db_set({
        "status": "sending", "queued_at": frappe.utils.now_datetime(),
        "total_recipients": len(targets), "skipped_opt_out_count": skipped,
        "sent_count": 0, "delivered_count": 0, "read_count": 0, "failed_count": 0,
    })

    for r in targets:
        log = frappe.get_doc({
            "doctype": "WhatsApp Message Log", "post": post_name,
            "recipient": r.name, "phone_number": r.phone_number, "status": "queued",
        }).insert(ignore_permissions=True)
        if _inline:
            send_single(log.name)
        else:
            frappe.enqueue(
                "whatsapp_broadcast.tasks.sender.send_single",
                log_name=log.name, queue="long", timeout=120,
            )

    if _inline:
        _finalize(post_name)
    else:
        frappe.enqueue(
            "whatsapp_broadcast.tasks.sender._finalize", post_name=post_name,
            queue="long", timeout=60, enqueue_after_commit=True,
        )


def send_single(log_name: str) -> None:
    log = frappe.get_doc("WhatsApp Message Log", log_name)
    post = frappe.get_doc("WhatsApp Post", log.post)
    tpl = frappe.get_doc("WhatsApp Template", post.template)
    s = frappe.get_single("WhatsApp Settings")
    bucket = _bucket(int(s.rate_limit_per_second or 80))
    recipient = frappe.get_doc("WhatsApp Recipient", log.recipient)

    last_err = None
    for attempt in range(int(s.max_retries_5xx or 3) + 1):
        bucket.acquire()
        try:
            resp = meta_client.send_template(
                to=log.phone_number,
                template_name=tpl.template_name, lang=tpl.language,
                components=_build_components(tpl, post, recipient),
            )
            mid = resp["messages"][0]["id"]
            log.db_set({"meta_message_id": mid, "status": "sent",
                        "sent_at": frappe.utils.now_datetime(), "retry_count": attempt})
            _bump(post.name, "sent_count")
            _publish_progress(post.name)
            return
        except meta_client.MetaAPIError as e:
            last_err = e
            if not e.retryable:
                break
            time.sleep(min(16, 4 ** attempt))

    log.db_set({"status": "failed",
                "error_code": str(last_err.meta_code or last_err.status_code),
                "error_message": last_err.meta_message,
                "retry_count": attempt})
    _bump(post.name, "failed_count")
    _publish_progress(post.name)


def _bump(post_name: str, field: str) -> None:
    frappe.db.sql(
        f"UPDATE `tabWhatsApp Post` SET `{field}` = COALESCE(`{field}`, 0) + 1 WHERE name = %s",
        (post_name,),
    )


def _finalize(post_name: str) -> None:
    post = frappe.get_doc("WhatsApp Post", post_name)
    if (post.sent_count or 0) + (post.failed_count or 0) < (post.total_recipients or 0):
        return
    final = "failed" if post.failed_count == post.total_recipients and post.total_recipients > 0 else "completed"
    post.db_set({"status": final, "completed_at": frappe.utils.now_datetime()})
    _publish_progress(post_name)


@frappe.whitelist()
def trigger_send(post_name: str) -> None:
    frappe.get_doc("WhatsApp Post", post_name)  # permission check
    post = frappe.get_doc("WhatsApp Post", post_name)
    validate_for_send(post)
    post.db_set("status", "queued")
    frappe.enqueue(
        "whatsapp_broadcast.tasks.sender.send_post",
        post_name=post_name, queue="long", timeout=600, enqueue_after_commit=True,
    )
```

- [ ] **Step 5: Run integration tests pass**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_send_integration
```
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): message log + RQ sender with token-bucket and retries"
```

---

## Task 11: Webhook → Post counter integration test

**Files:**
- Modify: `whatsapp_broadcast/whatsapp_broadcast/tests/test_webhook.py`

- [ ] **Step 1: Append integration test**

```python
import json, hmac, hashlib
from unittest.mock import patch


class TestWebhookStatusFlow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        s = frappe.get_single("WhatsApp Settings")
        s.app_secret = "SECRET"; s.webhook_verify_token = "VT"
        s.save(ignore_permissions=True); frappe.db.commit()

    def test_delivered_status_updates_log_and_post(self):
        # Seed a post + log
        if not frappe.db.exists("WhatsApp Template", "wh_tpl"):
            frappe.get_doc({"doctype": "WhatsApp Template", "template_name": "wh_tpl",
                            "language": "de", "category": "MARKETING",
                            "header_type": "none", "body_text": "x",
                            "meta_status": "approved"}).insert(ignore_permissions=True)
        if not frappe.db.exists("WhatsApp Recipient", "+491702222201"):
            frappe.get_doc({"doctype": "WhatsApp Recipient", "recipient_name": "W",
                            "phone_number": "+491702222201", "opt_in_status": "opted_in"}).insert(ignore_permissions=True)
        post = frappe.get_doc({"doctype": "WhatsApp Post", "title": "wh1",
                               "template": "wh_tpl", "variable_values": "{}",
                               "recipient_mode": "explicit_list",
                               "explicit_recipients": [{"recipient": "+491702222201"}],
                               "total_recipients": 1}).insert(ignore_permissions=True)
        log = frappe.get_doc({"doctype": "WhatsApp Message Log", "post": post.name,
                              "recipient": "+491702222201", "phone_number": "+491702222201",
                              "status": "sent", "meta_message_id": "wamid.WH1"}).insert(ignore_permissions=True)

        payload = {"entry": [{"changes": [{"value": {"statuses": [
            {"id": "wamid.WH1", "status": "delivered", "timestamp": "1716220800"}
        ]}}]}]}
        raw = json.dumps(payload).encode()
        sig = "sha256=" + hmac.new(b"SECRET", raw, hashlib.sha256).hexdigest()

        from werkzeug.wrappers import Request
        from werkzeug.test import EnvironBuilder
        env = EnvironBuilder(method="POST", data=raw,
                             headers={"X-Hub-Signature-256": sig,
                                      "Content-Type": "application/json"}).get_environ()
        with patch.object(frappe.local, "request", Request(env)):
            from whatsapp_broadcast.api.webhook import handle
            result = handle()
        self.assertEqual(result, {"ok": True})
        post.reload(); log.reload()
        self.assertEqual(log.status, "delivered")
        self.assertEqual(post.delivered_count, 1)
```

- [ ] **Step 2: Run, expected to pass**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast --module whatsapp_broadcast.tests.test_webhook
```
Expected: previous 5 + new 1 = 6 PASS.

- [ ] **Step 3: Commit**

```bash
git add whatsapp_broadcast
git commit -m "test(whatsapp): webhook → post counter integration test"
```

---

## Task 12: Post form JS (preview + live recipient count + Send + realtime)

**Files:**
- Create: `whatsapp_broadcast/whatsapp_broadcast/api/post_helpers.py`
- Create: `whatsapp_broadcast/whatsapp_broadcast/public/js/whatsapp_post.js`

- [ ] **Step 1: Create whitelisted helpers**

`whatsapp_broadcast/whatsapp_broadcast/api/post_helpers.py`:
```python
import json
import frappe
from whatsapp_broadcast.whatsapp_broadcast.doctype.whatsapp_post.whatsapp_post import (
    expand_recipients, validate_for_send,
)


@frappe.whitelist()
def preview(post_name: str) -> dict:
    post = frappe.get_doc("WhatsApp Post", post_name)
    tpl = frappe.get_doc("WhatsApp Template", post.template)
    vars_ = json.loads(post.variable_values or "{}")
    body = tpl.body_text or ""
    for k, v in vars_.items():
        body = body.replace(f"{{{{{k}}}}}", str(v))
    return {
        "header_type": tpl.header_type,
        "header_content": tpl.header_content,
        "body": body,
        "footer": tpl.footer_text,
        "buttons": [{"type": b.button_type, "text": b.text} for b in (tpl.buttons or [])],
    }


@frappe.whitelist()
def recipient_count(post_name: str) -> dict:
    targets, skipped = expand_recipients(post_name)
    return {"total": len(targets), "skipped_opt_out": skipped}
```

- [ ] **Step 2: Create the form script**

`whatsapp_broadcast/whatsapp_broadcast/public/js/whatsapp_post.js`:
```javascript
frappe.ui.form.on('WhatsApp Post', {
    refresh(frm) {
        _render_preview(frm);
        _render_count(frm);
        if (!frm.is_new() && ['draft', 'failed'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Send'), () => _confirm_send(frm), __('Actions'));
        }
        if (frm.doc.status === 'sending' || frm.doc.status === 'queued') {
            _subscribe_progress(frm);
        }
    },
    template: _render_preview,
    variable_values: _render_preview,
    recipient_mode: _render_count,
    recipient_tags_add: _render_count,
    recipient_tags_remove: _render_count,
    explicit_recipients_add: _render_count,
    explicit_recipients_remove: _render_count,
});

function _format(text) {
    if (!text) return '';
    return frappe.utils.escape_html(text)
        .replace(/\*([^*]+)\*/g, '<b>$1</b>')
        .replace(/_([^_]+)_/g, '<i>$1</i>')
        .replace(/~([^~]+)~/g, '<s>$1</s>')
        .replace(/```([\s\S]+?)```/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

function _render_preview(frm) {
    if (!frm.doc.template || frm.is_new()) return;
    frappe.call({
        method: 'whatsapp_broadcast.api.post_helpers.preview',
        args: { post_name: frm.doc.name },
        callback: (r) => {
            const p = r.message || {};
            const html = `
                <div style="max-width:340px;background:#dcf8c6;padding:8px 12px;border-radius:8px;font-family:system-ui;">
                  ${p.header_content ? `<div style="font-weight:600;margin-bottom:4px;">${frappe.utils.escape_html(p.header_content)}</div>` : ''}
                  <div>${_format(p.body)}</div>
                  ${p.footer ? `<div style="color:#888;font-size:12px;margin-top:4px;">${frappe.utils.escape_html(p.footer)}</div>` : ''}
                  ${(p.buttons || []).map(b => `<div style="margin-top:6px;color:#1a73e8;">${frappe.utils.escape_html(b.text)}</div>`).join('')}
                </div>`;
            frm.dashboard.clear_headline();
            frm.dashboard.add_section(html, __('Preview'));
        },
    });
}

function _render_count(frm) {
    if (frm.is_new()) return;
    frappe.call({
        method: 'whatsapp_broadcast.api.post_helpers.recipient_count',
        args: { post_name: frm.doc.name },
        callback: (r) => {
            const m = r.message || {};
            frm.dashboard.set_headline_alert(
                `Recipients: <b>${m.total}</b> &nbsp; Skipped (opt-out): <b>${m.skipped_opt_out}</b>`
            );
        },
    });
}

function _confirm_send(frm) {
    frappe.call({
        method: 'whatsapp_broadcast.api.post_helpers.recipient_count',
        args: { post_name: frm.doc.name },
        callback: (r) => {
            const m = r.message || {};
            frappe.confirm(
                __(`Send to ${m.total} recipients via template "${frm.doc.template}"?`),
                () => {
                    frappe.call({
                        method: 'whatsapp_broadcast.tasks.sender.trigger_send',
                        args: { post_name: frm.doc.name },
                        callback: () => { frappe.show_alert({message: 'Queued', indicator: 'green'}); frm.reload_doc(); },
                    });
                }
            );
        },
    });
}

function _subscribe_progress(frm) {
    frappe.realtime.on('whatsapp_post_progress', (data) => {
        if (data.post === frm.doc.name) {
            frm.reload_doc();
        }
    });
}
```

- [ ] **Step 3: Rebuild assets**

```bash
docker compose exec backend bash -lc "cd /home/frappe/frappe-bench && bench build --app whatsapp_broadcast"
```

- [ ] **Step 4: Manual verify**

Open a Post in Desk:
- Preview bubble renders with formatting applied.
- Recipient count headline updates when changing tags.
- "Send" button visible in draft state; confirm dialog shows recipient count.
- After Send: status flips to `queued` → `sending` → `completed`, counters increment live (requires real Meta creds or mocked HTTP — for now the form will fail at API call without creds; that's OK).

- [ ] **Step 5: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): Post form preview, live recipient count, Send button, realtime progress"
```

---

## Task 13: Workspace + role fixtures

**Files:**
- Create: `whatsapp_broadcast/whatsapp_broadcast/fixtures/role.json`
- Create: `whatsapp_broadcast/whatsapp_broadcast/whatsapp_broadcast/workspace/whatsapp_broadcast/whatsapp_broadcast.json`

- [ ] **Step 1: Create role fixture**

`fixtures/role.json`:
```json
[
  {"doctype": "Role", "role_name": "WhatsApp Manager", "desk_access": 1},
  {"doctype": "Role", "role_name": "WhatsApp User", "desk_access": 1}
]
```

- [ ] **Step 2: Create workspace JSON**

`workspace/whatsapp_broadcast/whatsapp_broadcast.json`:
```json
{
 "doctype": "Workspace",
 "name": "WhatsApp Broadcast",
 "label": "WhatsApp Broadcast",
 "title": "WhatsApp Broadcast",
 "module": "WhatsApp Broadcast",
 "public": 1,
 "is_hidden": 0,
 "sequence_id": 50,
 "content": "[{\"type\":\"header\",\"data\":{\"text\":\"<span class=\\\"h4\\\">WhatsApp Broadcast</span>\",\"col\":12}}]",
 "links": [
  {"label":"Posts","link_type":"DocType","link_to":"WhatsApp Post","type":"Link"},
  {"label":"Templates","link_type":"DocType","link_to":"WhatsApp Template","type":"Link"},
  {"label":"Recipients","link_type":"DocType","link_to":"WhatsApp Recipient","type":"Link"},
  {"label":"Tags","link_type":"DocType","link_to":"WhatsApp Tag","type":"Link"},
  {"label":"Message Log","link_type":"DocType","link_to":"WhatsApp Message Log","type":"Link"},
  {"label":"Settings","link_type":"DocType","link_to":"WhatsApp Settings","type":"Link"}
 ],
 "shortcuts": [],
 "roles": []
}
```

- [ ] **Step 3: Migrate + verify**

```bash
make migrate
```
Visit `http://localhost:8080/app/whatsapp-broadcast`. Workspace shows all DocTypes in sidebar.

- [ ] **Step 4: Commit**

```bash
git add whatsapp_broadcast
git commit -m "feat(whatsapp): workspace + role fixtures"
```

---

## Task 14: Configure Meta webhook URL + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the webhook URL**

Append a new section to repo `README.md`:

```markdown
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

Tests:
```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast
```
```

- [ ] **Step 2: Run full test suite**

```bash
docker compose exec backend bench --site frontend run-tests --app whatsapp_broadcast
```
Expected: all tests across modules pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(whatsapp): document broadcast app setup + webhook configuration"
```

---

## Done

App is feature-complete per the design spec: scaffold + Docker integration, all DocTypes (Settings, Tag, Recipient, Template + Button, Post + children, Message Log), Meta API wrapper, token-bucket throttle, webhook with HMAC verification + counter updates, queue-based fan-out send with retries, custom Post form with preview/count/Send/realtime progress, workspace, roles, README.

Next steps (out of v1 scope, captured in spec): scheduled sends, dashboard analytics, inbound message handling, multi-WABA support.
