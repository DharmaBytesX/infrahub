---
Title: Saved Views
Author:
  - Paul Lemesle
Status: draft (placeholder)
---

# Saved Views

## Summary

Named, reusable presets of filter / sort / column visibility / (later) other view state, scoped to a schema kind. Personal first; sharing follows in a later phase. Lives in its own schema node so the user-preference surface stays small.

This spec is a **placeholder** — owner and acceptance criteria need refinement before we cut tickets for the implementation.

## Problem Statement

- Users repeatedly reconstruct the same filter combinations on list pages ("my open proposed changes", "repos on this branch").
- There is no way to share a curated view with a teammate.
- Implementations of "remember the last view" leak into individual pages instead of a generic mechanism.

## Solution Overview

Schema node `CoreSavedView` (per-account, per-schema-kind, named). Owner-only in V1 of this feature; sharing via groups + direct accounts in V2.

Selection of a saved view is recorded in `CoreUserPreference` (`selected_saved_views: JSON` map of `schema_kind → saved_view_id`) so reopening a list page restores it.

## Proposed Schema (sketch)

| Attribute | Kind | Notes |
|---|---|---|
| `name` | Text | Unique per (owner, schema_kind) |
| `description` | Text | Optional |
| `schema_kind` | Text | E.g. `CoreRepository` |
| `filters` | JSON | Frontend-owned shape |
| `sort` | JSON | Optional |
| `visible_columns` | JSON | Optional |

Relationships:

- `owner` → `CoreGenericAccount`, cardinality ONE, required, `on_delete: cascade`.

V2 additions for sharing:

- `shared_with_groups` → `CoreAccountGroup`, cardinality MANY.
- `shared_with_accounts` → `CoreGenericAccount`, cardinality MANY.

A view is private iff both share relationships are empty — no `visibility` enum.

## GraphQL (sketch)

- Standard CRUD on `CoreSavedView`.
- Custom owner-and-shared query `InfrahubMySavedViews(schema_kind: String)` returning views the caller owns plus (V2) views shared with them.
- Custom mutation `InfrahubSavedViewFork(id)` — duplicate a shared view into one owned by the caller.

## Frontend (sketch)

- "Save current view as…" action on list pages.
- View picker in the page toolbar.
- Settings page: list of all owned views + delete/rename + (V2) "Share…" dialog.
- Resolution order on page load:
  1. View ID in URL query param (deep link).
  2. `selected_saved_views[kind]` from `CoreUserPreference`.
  3. Saved-filter from the saved-filters feature (if it lands first; see `2026-04-saved-filters.md`).
  4. Page's built-in defaults.

## Out of Scope

- Folder / hierarchy of views.
- Cross-tenant or cross-account view import/export.
- Server-side rendering of view-driven exports.

## Open Questions

- **Sharing model ordering.** Ship V1 owner-only, or include group-level sharing from day one? Owner-only is the safer cut — less permission surface to validate.
- **Reuse `LINEAGEOWNER`** generic for `CoreSavedView.owner` instead of a bespoke relationship? Saves an attribute and gets audit trail for free, but only if write authorization keys off lineage cleanly.
- **Ad-hoc edits on top of an active saved view** — drop the selection on first edit, or require an explicit "Save as / Update view" step?
- **What state qualifies as "view state"** beyond filter/sort/columns? Schema graph fold/zoom positions? Diff page tab selection? Decide before V1 to avoid retrofits.

## Dependencies

- Lands after the user-preferences foundation (`2026-04-user-preferences.md`) so `selected_saved_views` has a place to live.
- Independent of the saved-filters feature, but sequencing matters: if saved filters ships first, the resolution order needs to account for it.
