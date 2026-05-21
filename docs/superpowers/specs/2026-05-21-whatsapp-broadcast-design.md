# WhatsApp Broadcast App — Design

**Status:** Draft
**Date:** 2026-05-21
**Author:** johann.bechtold@gmail.com

## Goal

Add a Frappe app `whatsapp_broadcast` to the lumeapps-v2 ERPNext stack that lets authorized users compose, store, and send WhatsApp messages to a managed list of recipients via the official Meta WhatsApp Cloud API, using a template-only broadcast model with rich-text and media support, full per-recipient delivery tracking, and queue-based rate-limited sending.

## Background & Constraints

- The WhatsApp Cloud API (Meta, official) does **not** support posting into WhatsApp groups. Only 1:1 messages are supported.
- Outside the 24-hour customer service window, only **pre-approved message templates** can be sent. This app uses a template-only model: every send is a template instance.
- Templates must be created in Meta Business Manager **or** submitted via API and approved by Meta before they can be used.
- Templates support: header (text/image/video/document), body (max 1024 chars, `{{n}}` variables, `*bold*`/`_italic_`/`~strike~`/```` ```mono``` ```` formatting), footer (max 60 chars), buttons (quick reply / URL / phone).
- Recipients must have opted in. The app tracks opt-in status but does not enforce double-opt-in collection (admin responsibility).
- Existing stack: ERPNext on Frappe v16, Docker Compose, custom image bakes in `sensor_monitor` app. New app follows the same baking pattern.

## High-Level Architecture

New Frappe app `whatsapp_broadcast` installed alongside `sensor_monitor` in the custom ERPNext image. App provides:

- DocTypes for credentials, recipients, templates, posts (= broadcast jobs), and per-message delivery logs.
- Background workers (Frappe RQ) for rate-limited fan-out sending.
- A whitelisted REST endpoint for the Meta status webhook.
- Frappe Desk forms for management, plus a custom Post form with live preview.

```
Template create → Submit to Meta → (Meta approval webhook OR manual sync)
                                       ↓
Post create → Template + Variables + Filter → Preview → Send
                                       ↓
                            RQ: send_post (expand recipients)
                                       ↓
                            RQ: send_single × N (token-bucket throttled)
                                       ↓
                            Meta API → message_id → Message Log
                                       ↓
                            Meta Webhook → status updates → Message Log
```

## DocTypes

### WhatsApp Settings (Single)

| Field | Type | Notes |
|---|---|---|
| `phone_number_id` | Data | Meta Cloud API phone-number id |
| `business_account_id` | Data | WABA id |
| `access_token` | Password | Long-lived system-user token |
| `webhook_verify_token` | Password | Set in Meta webhook config |
| `app_secret` | Password | For HMAC verification of webhook payloads |
| `default_language` | Data | Default `de` |
| `rate_limit_per_second` | Int | Default 80 |
| `max_retries_5xx` | Int | Default 3 |

Permissions: System Manager only.

### WhatsApp Recipient

| Field | Type | Notes |
|---|---|---|
| `recipient_name` | Data | Required |
| `phone_number` | Data | E.164 format, unique, validated |
| `opt_in_status` | Select | `pending` / `opted_in` / `opted_out` |
| `opt_in_date` | Datetime | Set when status moves to `opted_in` |
| `tags` | Table MultiSelect | Links to `WhatsApp Tag` |
| `notes` | Small Text | Free-form |

Permissions: WhatsApp Manager.

### WhatsApp Tag

Simple `tag_name` (unique). Used to group recipients for filtering.

### WhatsApp Template

| Field | Type | Notes |
|---|---|---|
| `template_name` | Data | Meta-compatible: `[a-z0-9_]+`, unique |
| `language` | Data | e.g. `de`, `en_US` |
| `category` | Select | `MARKETING` / `UTILITY` / `AUTHENTICATION` |
| `header_type` | Select | `none` / `text` / `image` / `video` / `document` |
| `header_content` | Small Text | Text for text-headers; ignored for media (media supplied per Post) |
| `body_text` | Text | Max 1024 chars, supports WA formatting + `{{n}}` |
| `footer_text` | Data | Max 60 chars |
| `buttons` | Table | Child: `WhatsApp Template Button` |
| `meta_status` | Select | `local` / `pending` / `approved` / `rejected` / `paused` |
| `meta_template_id` | Data | Set after submission |
| `rejection_reason` | Small Text | If rejected |
| `variable_count` | Int | Computed from `body_text` on save |

Actions (Desk buttons):

- **Submit to Meta** — POST template to Graph API, status → `pending`.
- **Sync Status** — GET template status from Graph API, update local fields.

Validation: only `approved` templates may be referenced by a Post that is being sent.

### WhatsApp Template Button (Child)

| Field | Type |
|---|---|
| `button_type` | Select `quick_reply` / `url` / `phone` |
| `text` | Data |
| `url_or_phone` | Data |

### WhatsApp Post

| Field | Type | Notes |
|---|---|---|
| `title` | Data | Internal label |
| `template` | Link → WhatsApp Template | Required, must be `approved` to send |
| `variable_values` | JSON | `{"1": "Hans", "2": "10€"}` |
| `media_attachment` | Attach | File for media-header templates; uploaded to Meta on send, id cached |
| `media_id_cache` | Data | Meta media id after upload |
| `recipient_mode` | Select | `by_tags` / `explicit_list` |
| `recipient_tags` | Table MultiSelect | If `by_tags` |
| `explicit_recipients` | Table | Child rows linking to WhatsApp Recipient |
| `status` | Select | `draft` / `queued` / `sending` / `completed` / `failed` |
| `total_recipients` | Int | Computed at queue time |
| `sent_count` | Int | |
| `delivered_count` | Int | |
| `read_count` | Int | |
| `failed_count` | Int | |
| `skipped_opt_out_count` | Int | |
| `created_by` | Link → User | |
| `queued_at` | Datetime | |
| `completed_at` | Datetime | |

Actions: **Preview** (renders bubble), **Send** (validate + enqueue).

### WhatsApp Message Log

One row per (Post × Recipient).

| Field | Type | Notes |
|---|---|---|
| `post` | Link → WhatsApp Post | |
| `recipient` | Link → WhatsApp Recipient | |
| `phone_number` | Data | Snapshot at send time |
| `meta_message_id` | Data | Indexed; used by webhook lookup |
| `status` | Select | `queued` / `sent` / `delivered` / `read` / `failed` |
| `error_code` | Data | Meta error code if failed |
| `error_message` | Small Text | |
| `sent_at` | Datetime | |
| `delivered_at` | Datetime | |
| `read_at` | Datetime | |
| `retry_count` | Int | |
| `raw_webhook_payload` | JSON | Last received status event, for audit |

## Components

### `whatsapp_broadcast/api/meta_client.py`

Thin wrapper around Graph API. Reads credentials from `WhatsApp Settings`. Functions:

- `send_template(to: str, template_name: str, lang: str, components: list) -> dict` — returns Meta response incl. `messages[0].id`.
- `upload_media(file_path: str, mime_type: str) -> str` — returns Meta media id.
- `submit_template(payload: dict) -> dict` — POST `/{waba_id}/message_templates`.
- `get_template_status(name: str, lang: str) -> dict` — for sync.

Error mapping: raises `MetaAPIError` with `status_code`, `meta_code`, `meta_message`. Caller decides retry policy.

### `whatsapp_broadcast/api/webhook.py`

Whitelisted endpoint exposed at `/api/method/whatsapp_broadcast.api.webhook.handle`.

- `GET`: returns `hub.challenge` if `hub.verify_token` matches Settings.
- `POST`:
  1. Read raw body, compute HMAC-SHA256 with `app_secret`, compare to `X-Hub-Signature-256`. On mismatch → 403 + log.
  2. Parse payload. For each `statuses[]` entry, look up `WhatsApp Message Log` by `meta_message_id`, update status + timestamp, store `raw_webhook_payload`, increment matching Post counter (atomic via `frappe.db.sql` `UPDATE … SET col = col + 1`).
  3. Inbound `messages[]` (if any) are logged to `raw_webhook_payload` of a synthetic audit doctype but otherwise ignored (template-only model).
  4. Always return 200 unless signature failed.

### `whatsapp_broadcast/tasks/sender.py`

RQ job `send_post(post_name)`:

1. Load Post, set `status=sending`, `queued_at=now`.
2. Expand recipients per `recipient_mode`. Filter to `opt_in_status == opted_in`. Count `skipped_opt_out_count` from the difference.
3. Set `total_recipients`.
4. If template uses media header, upload media once (cache `media_id_cache`).
5. For each recipient: create `Message Log` row with `status=queued`, enqueue `send_single(log_name)`.
6. When all per-recipient jobs complete (RQ job dependency), set Post `status=completed` (or `failed` if `failed_count == total_recipients`), `completed_at=now`.

RQ job `send_single(log_name)`:

1. Token-bucket throttle (Redis-backed, capacity = `rate_limit_per_second`).
2. Call `meta_client.send_template`.
3. On success: update Log `status=sent`, `meta_message_id`, `sent_at`; increment Post `sent_count`.
4. On 4xx: update Log `status=failed`, `error_*`; increment `failed_count`. No retry.
5. On 5xx / network: increment `retry_count`, exponential backoff (1s, 4s, 16s), max `max_retries_5xx`. After exhaustion → `failed`.

Realtime publish (`frappe.publish_realtime`) on each counter change so the Post form UI updates live.

### Frontend

- Settings, Recipient, Tag, Template, Template Button: standard Frappe Desk forms.
- **Post form** (custom client script `whatsapp_post.js`):
  - Live preview panel that renders the template body with current `variable_values` substituted, applies WA-style formatting (regex → HTML), and shows header media / footer / buttons in a WhatsApp-bubble layout.
  - Live recipient count when `recipient_tags` or `explicit_recipients` change (server call to a whitelisted helper).
  - "Send" button: confirmation dialog showing recipient count + template name, then triggers server action.
  - Progress section that subscribes to realtime events for `sent_count` / `failed_count` etc.
- A "WhatsApp Broadcast" workspace groups all DocTypes for easy access.

(A dashboard page analogous to `sensor_monitor` is out of scope for v1.)

## Error Handling

| Failure | Behavior |
|---|---|
| Meta 4xx (invalid recipient, template not approved, opted-out at Meta level) | Log `failed`, no retry. |
| Meta 429 (rate limit) | Treat as 5xx: backoff + retry. |
| Meta 5xx / network | Exponential backoff up to `max_retries_5xx`, then `failed`. |
| Webhook signature mismatch | 403, log warning, no DB write. |
| Opt-out recipient in selection | Excluded at expansion, counted in `skipped_opt_out_count`. |
| Send pressed on non-approved template | Validation error before enqueue. |
| Send pressed on Post with missing variable values | Validation error before enqueue (count of `{{n}}` in template must equal keys in `variable_values`). |
| Media-header template without `media_attachment` | Validation error before enqueue. |

## Security

- `access_token`, `app_secret`, `webhook_verify_token` stored as Frappe Password fields (encrypted at rest).
- Webhook HMAC verification mandatory; missing/invalid signature → 403.
- DocType permissions:
  - `WhatsApp Settings`: System Manager only.
  - All other DocTypes: new role `WhatsApp Manager`. Read for `WhatsApp User` (view-only).
- Phone numbers in logs are PII; access restricted to the same roles.
- No inbound message bodies are persisted (only metadata in audit payload) to minimize PII surface.

## Testing

**Unit:**

- `meta_client` with `responses` library mocking Graph API (success, 4xx, 5xx, rate-limit).
- Token-bucket throttle correctness (concurrent calls don't exceed budget).
- Webhook HMAC verification (valid / invalid / missing header).
- Recipient expansion: tag filter, explicit list, opt-out exclusion, deduplication when same recipient matches multiple tags.
- Template body variable count derivation.
- Post send-time validation rules.

**Integration:**

- Full Post send cycle against a mock Meta server: enqueue → fan-out → per-recipient logs → counter updates → webhook delivery events → final Post status.
- Template submit + status sync round-trip.

Use Frappe's `FrappeTestCase` patterns; mock RQ to run inline for integration tests.

## Packaging & Deployment

- New app at repo root: `whatsapp_broadcast/` (sibling of `sensor_monitor/`).
- `Dockerfile` extended:
  - Copy `whatsapp_broadcast` into the image.
  - `bench get-app --branch ... whatsapp_broadcast` (editable install) or local-path install, same pattern as `sensor_monitor`.
  - `bench build --app whatsapp_broadcast` to bundle assets (custom Post form JS).
- `docker-compose.yml` `create-site` step extended to `--install-app whatsapp_broadcast`.
- `Makefile`: extend `install-app` target if needed; no other changes required.
- No new external Python deps beyond `requests` (already present in Frappe env). Optional: `redis` token bucket uses the Redis already in the stack.

## Out of Scope (v1)

- Inbound message handling / two-way conversations.
- Template editor UI beyond standard Frappe forms (e.g. drag-drop button builder).
- Multi-WABA / multi-phone-number support.
- Scheduled (cron) sends — possible v2 (`send_at` field + cron job).
- Dashboard analytics page.
- Bulk recipient CSV import UI (use Frappe's standard import for v1).

## Open Questions

None at design time. Implementation plan will surface concrete file layouts and ordering.
