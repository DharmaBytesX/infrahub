---
Title: "Show Extra Fields" Toggle Persistence
Author:
  - Paul Lemesle
Status: draft (placeholder — needs design pass)
---

# "Show Extra Fields" Toggle Persistence

## Summary

The object/list views have a toggle for showing/hiding "extra" attributes and relationships. Today the toggle state does not persist. Persisting it sounds simple, but the right behaviour is non-obvious — hence this dedicated spec.

This is a **placeholder**: shape and scope are open.

## Problem Statement

- User toggles "show extra fields" on, navigates away, comes back, toggle is off.
- Across multiple object kinds, the right default may differ — a user inspecting `CoreRepository` may want every attribute visible, but on `IpamIPAddress` the compact view is enough.
- A naive global boolean ("always show extras") is probably wrong; a per-kind boolean might be the right shape but adds complexity.

## Why This Is Not in the User-Preferences V1

- The exact attribute name should match what the toggle is called in the UI today, and the toggle's wording is itself under discussion.
- The semantics of "extra" are coupled to the schema: the set of fields hidden behind the toggle changes as the schema evolves.
- The right scoping (global, per-kind, per-page-instance) needs a design pass before we burn a column.

## Candidate Designs

### A — Single global boolean

Attribute `show_extra_fields: Boolean` on `CoreUserPreference`. Lowest cost, lowest fidelity.

### B — Per-kind map

Attribute `show_extra_fields: JSON` on `CoreUserPreference`, map `schema_kind → boolean`. Higher fidelity, but the user has to teach the toggle on every kind.

### C — Per-kind override on top of a global default

Two attributes: a global default plus a per-kind override map. Closest to what users probably want but the most logic.

### D — Roll into saved views

Treat field visibility as part of a saved view's `visible_columns` / "visible fields" payload. No separate persistence; users get persistence for free when they save a view. Punts the implicit-persistence question entirely.

Lean: **D** if the saved-views feature lands soon. Otherwise **A** as a low-cost interim.

## Frontend Considerations

- The toggle wording in the current UI needs to be located and confirmed before naming the attribute.
- If we go with B/C, an upgrade path for the "list of kinds" needs to handle schema renames.

## Out of Scope

- Re-designing the underlying "extra field" classification.
- Redefining what counts as "extra" per kind.

## Open Questions

- **Is this even a top-50 user request**, or are we solving a problem we noticed but users don't notice?
- **Default-on or default-off** for new users? Does the answer differ per kind?
- **Coupling to saved views.** If saved views can pin column/field visibility per kind, do we need a separate persistence path at all?
- **Naming.** Match the UI wording — locate the toggle in `frontend/app/src/entities/objects/` (object detail) and `frontend/app/src/entities/objects/ui/` (list view) before settling on an attribute name.

## Dependencies

- If we choose option D, this is a saved-views follow-up rather than a standalone feature.
- Otherwise depends on the user-preferences foundation (`2026-04-user-preferences.md`).
