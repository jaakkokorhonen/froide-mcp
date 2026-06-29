# Orchestration helpers

This document describes the orchestration layer built on top of the existing
Froide REST API. None of these features require changes to the Froide/Django
backend — they compose the existing `/api/v1/` endpoints into higher-level
operator workflows that guide work inside the existing Froide UI.

## Design principle

The orchestration helpers are **read-or-compose, never replace**. They help
an operator decide *what to do next* in the Froide UI; they do not try to
duplicate the UI or bypass Django's internal logic.

## Tools

### `triage_my_requests`

Build a prioritised work queue from the user's FOI requests.

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

## Planned tools (next iterations)

The following tools are identified for future versions and will be
implemented without backend changes:

| Tool | Purpose |
|---|---|
| `draft_followup_for_request` | Compose a follow-up message based on the request thread |
| `preflight_request_submission` | Validate a new request before submitting via `make_request` |
| `get_request_analytics` | Compute status distribution and counts across all visible requests |
| `draft_request` | Generate a FOI request body given a goal and a public body |
| `followup_after_deadline` | Find overdue requests and suggest follow-up language |
