---
Title: Saved Filters
Author:
  - Paul Lemesle
Status: draft (placeholder)
---

# Saved Filters

## Summary

Persist and restore the user's most recent filter selection per schema kind, so reopening a list page lands them back where they left off without rebuilding the filter from scratch. Distinct from saved views: this is **implicit, automatic, last-used**, not named or shared.

This spec is a **placeholder** — needs validation that "last-used filters" is the right product shape before tickets are cut.

## Problem Statement

- A user filters a list page, navigates away, comes back, and the filter is gone.
- Browser history can return them to the URL with query params, but the cross-device case (open the same page on a laptop after using a desktop) loses everything.
- The previous spec draft baked this into `CoreUserPreference.last_used_filters` (JSON map). That coupled it too tightly to the preferences surface, so it now lives on its own.

## Proposed Solution

Two options to evaluate before committing:

### Option A — Single JSON map on a new node

`CoreUserFilterState` (one per account):

| Attribute | Kind | Notes |
|---|---|---|
| `last_used` | JSON | Map `schema_kind → filter params` |

Pros: trivial schema, one read on page load, everything in one place.
Cons: opaque to GraphQL queries; can't be filtered/searched; one map grows unbounded.

### Option B — Per-kind row

`CoreUserFilterState` rows keyed by `(account, schema_kind)`:

| Attribute | Kind | Notes |
|---|---|---|
| `schema_kind` | Text | Required |
| `filters` | JSON | The filter params themselves |

Plus relationship `account` → `CoreGenericAccount`, cardinality ONE, `on_delete: cascade`.
Uniqueness on `(account, schema_kind)`.

Pros: GraphQL-queryable per kind, bounded write/read footprint per page load, plays nicer with a future "clear all" admin action.
Cons: more rows, slightly more boilerplate in CRUD.

Lean: **Option B**, unless the volume cost matters.

## Frontend Behaviour

- On page load: if a saved filter exists for the current kind, apply it (after URL params, after a saved view if one is active).
- On filter change: debounced write (suggested: 1 s after last change, flush on navigation).
- Reset action on the filter bar: clears the persisted state for that kind.

## GraphQL

- Standard CRUD on `CoreUserFilterState` (Option B).
- A custom query `InfrahubMyFilterState(schema_kind: String!)` for the read path so the page issues exactly one round trip.

## Permissions

- Owner-only read/write, same model as `CoreUserPreference`.

## Out of Scope

- Sharing or named filter sets — that's saved views.
- Filter validation against the schema (frontend trusts what it stored last; if the schema has changed, the filter is silently dropped or surfaced as a "stale filter" warning — UX TBD).

## Open Questions

- **Resolution order vs saved views.** If both features exist, does an active saved view always win? Lean: yes; saved-filters only applies when no view is selected.
- **Per-page granularity.** Is "schema_kind" the right key, or do we need per-page-instance keys (e.g. different list views of the same kind in different parts of the UI)?
- **Stale filter recovery.** What happens when a stored filter references a removed attribute? Drop silently, or warn the user once?
- **Discoverability.** Does the user see anywhere that "your filters are remembered"? Or is it purely magic?

## Dependencies

- None hard. Can ship before or after the user-preferences foundation, but the resolution-order decision must be coordinated with saved views (`2026-04-saved-views.md`).
