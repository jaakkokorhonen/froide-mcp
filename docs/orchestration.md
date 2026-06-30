# Orchestration helpers

This document describes the orchestration layer built on top of the existing
Froide REST API. None of these features require changes to the Froide/Django
backend — they compose the existing `/api/v1/` endpoints into higher-level
operator workflows that guide work inside the existing Froide UI.

## Design principle

The orchestration helpers are **read-or-compose, never replace**. They help
an operator decide *what to do next* in the Froide UI; they do not try to
duplicate the UI or bypass Django’s internal logic.

## Tools

### `triage_my_requests`

Build a prioritised work queue from the user’s FOI requests.

**What it does:** Queries the Froide API across the most actionable request
statuses (`requires_user_action`, `has_fee`, `awaiting_classification`, etc.),
scores each result by urgency, deduplicates, and returns a ranked list with
a plain-language suggested next step for each request.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `statuses` | `list[str] \| None` | All urgent statuses | Override the statuses to query |
| `query` | `str \| None` | — | Free-text filter forwarded to Froide search |
| `page` | `int` | `1` | Page number for each per-status API call |

**Priority scoring:**

| Score | Statuses / condition |
|---|---|
| 100 | `requires_user_action`, `awaiting_user_confirmation`, `has_fee` |
| 90 | `awaiting_classification`, `classification_needed` |
| 80 | `publicbody_needed`, `awaiting_publicbody_confirmation` |
| 70 | `awaiting_response` |
| 60 | Free-text fields contain action keywords (heuristic) |
| 50 | Everything else (general review queue) |
| 30 | `partially_successful`, `successful` |
| 20 | `refused`, `not_held`, `gone_postal`, `user_withdrew`, `resolved` |

**Returns:** `{ statuses_queried, count, items[] }` where each item carries
`request_id`, `label`, `status`, `priority`, `why`, `next_step`.

---

### `find_requests_needing_action`

A focused subset of `triage_my_requests` that returns only the requests that
most likely need a human decision soon (urgent status group **or** priority ≥ 80).

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | `str \| None` | — | Free-text filter |
| `page` | `int` | `1` | Page number |

**Returns:** `{ count, items[], guidance }` — same item shape as
`triage_my_requests`, plus a `guidance` string.

---

### `summarize_request_thread`

Produce a short operator briefing for a single request thread.

Fetches the request and its attachments, then returns message count,
attachment count, current priority score and the suggested next manual step.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `request_id` | `int` | Froide request ID |

**Returns:**
```json
{
  "request_id": 42,
  "label": "#42 Access to procurement records",
  "status": "awaiting_response",
  "message_count": 3,
  "attachment_count": 1,
  "priority": 70,
  "why": "waiting for authority response",
  "next_step": "Check whether the statutory deadline is near or exceeded, then prepare a follow-up if needed."
}
```

---

### `draft_followup_for_request`

Draft a status-aware follow-up message for an existing request thread.

**What it does:** Fetches the request and its latest message, then returns a
suggested subject line and draft message body based on the current status.
Does **not** send anything — the draft must be reviewed and passed to
`send_followup` by the operator.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `request_id` | `int` | Froide request ID |

**Returns:**
```json
{
  "request_id": 42,
  "label": "#42 Access to procurement records",
  "status": "awaiting_response",
  "subject": "Follow-up on #42 Access to procurement records",
  "draft_message": "Dear ...",
  "latest_message_excerpt": "...",
  "why": "Check whether the statutory deadline is near or exceeded, then prepare a follow-up if needed."
}
```

---

### `preflight_request_submission`

Validate a prospective FOI request before calling `make_request`.

**What it does:** Performs MCP-side checks on subject, body, and the target
public body (resolved via the Froide API). Returns a list of blocking issues
and non-blocking warnings. Does **not** create a request.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `public_body_id` | `int` | — | ID of the target public body |
| `subject` | `str` | — | Request subject line |
| `body` | `str` | — | Request body text |
| `law_id` | `int \| None` | `None` | Froide law ID to apply |
| `campaign_id` | `int \| None` | `None` | Campaign to associate with |
| `public` | `bool` | `True` | Whether the request should be public |

**Returns:**
```json
{
  "ok": true,
  "issues": [],
  "warnings": ["Body is short; add more context..."],
  "request_preview": {
    "public_body_id": 7,
    "public_body_name": "Ministry of Finance",
    "subject": "Budget documents 2024",
    "body_preview": "...",
    "law_id": null,
    "law_name": null,
    "campaign_id": null,
    "campaign_name": null,
    "public": true
  },
  "next_step": "Call make_request if there are no blocking issues."
}
```

---

### `get_request_analytics`

Compute status distribution and priority bands across the user’s visible requests.

**What it does:** Delegates to `triage_my_requests` and aggregates the results
into status counts and four priority bands (critical / high / medium / low).
No backend aggregation endpoints are used.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `statuses` | `list[str] \| None` | All urgent statuses | Override the statuses to query |
| `page` | `int` | `1` | Page number |

**Returns:**
```json
{
  "count": 14,
  "statuses_queried": ["requires_user_action", "awaiting_response", "..."],
  "status_counts": {"awaiting_response": 8, "requires_user_action": 3, "...": 3},
  "priority_bands": {"critical": 2, "high": 1, "medium": 9, "low": 2},
  "top_requests": [...]
}
```

---

### `draft_request`

Draft a FOI request body from a user goal and the target public body.

**What it does:** Fetches the public body (and optionally the law) from the
Froide API, then produces a suggested subject line and a complete draft request
body. Does **not** submit anything — the draft can be reviewed or passed
directly to `preflight_request_submission` or `make_request`.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `public_body_id` | `int` | — | ID of the target public body |
| `goal` | `str` | — | Plain-language description of what the requester wants to achieve |
| `records_description` | `str` | — | Description of the specific records or information requested |
| `law_id` | `int \| None` | `None` | Froide law ID to reference in the draft |
| `public` | `bool` | `True` | Whether the resulting request should be public |

**Returns:**
```json
{
  "public_body_id": 5,
  "public_body_name": "Ministry of Finance",
  "subject": "Request for access to IT procurement invoices for fiscal year 2024",
  "draft_body": "Hello,\n\nI am requesting access to information held by ...",
  "law_id": null,
  "law_name": null,
  "public": true,
  "next_step": "Review the draft, then call preflight_request_submission or make_request directly."
}
```

---

### `followup_after_deadline`

Draft a statutory-deadline follow-up for a request that has exceeded its legal
response period.

**What it does:** Fetches the request and returns a ready-to-review draft
follow-up message that cites the missed deadline. Intended for use when the
status is `awaiting_response` and the statutory period has elapsed, or when a
refusal needs to be challenged. Does **not** send anything — the draft must be
reviewed and passed to `send_followup`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `request_id` | `int` | ID of the FOI request that has exceeded its deadline |

**Returns:**
```json
{
  "request_id": 5,
  "label": "#5 School budget data",
  "status": "awaiting_response",
  "subject": "Deadline follow-up: #5 School budget data",
  "draft_message": "Dear ...",
  "latest_message_excerpt": "...",
  "why": "Check whether the statutory deadline is near or exceeded, then prepare a follow-up if needed.",
  "note": "This draft is for statutory-deadline follow-up only. Review before sending via send_followup."
}
```
