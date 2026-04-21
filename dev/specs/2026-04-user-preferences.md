---
Title: User Preferences & Saved Views
Author:
  - Paul Lemesle
Status: draft
---

# User Preferences & Saved Views

## Summary

Introduce persistent, per-user UI preferences stored in the graph, replacing ad-hoc `localStorage` usage and enabling cross-device continuity. The V1 scope delivers a `CoreUserPreference` node covering date format, branch deletion default, extra-fields toggle, and implicit last-used filters. The design is forward-compatible with two later phases: personal saved views (V2) and shared saved views (V3), which live in a separate `CoreSavedView` node so the preference surface stays lean.

## Problem Statement

- UI preferences currently live in component state, URL query params (`nuqs`), or `localStorage`. Nothing survives a device switch, and nothing is discoverable by the backend or SDK.
- No shared concept of "my settings" exists. Each feature solves persistence in its own way.
- Users have no way to save and reuse filter combinations ("my pending changes"), nor to share curated views with teammates.

## Solution Overview

Two separate concerns, two separate entities:

| Entity | Purpose | Lifecycle | Phase |
|---|---|---|---|
| `CoreUserPreference` | Per-user UI defaults and implicit state | One per account, auto-created on first write | V1 |
| `CoreSavedView` | Named, reusable filter/sort/column presets | Many per account, explicit CRUD | V2 |
| `CoreSavedView` + sharing | Views visible to other users via groups | Same node, extended attributes | V3 |

Keeping these distinct prevents the preference node from growing into an unbounded bag of application state.

## V1 — User Preferences

### Backend

#### Schema node: `CoreUserPreference`

Defined in `backend/infrahub/core/schema/definitions/core/account.py` (colocated with `CoreAccount` / `AccountToken`).

- `name="UserPreference"`, `namespace="Core"`
- `branch=BranchSupportType.AGNOSTIC` (same as `AccountToken`)
- Relationship: `account` → `CoreGenericAccount`, `cardinality=ONE`, required, identifier `account__preferences`
- All attributes optional (user may only have set some)

Initial attributes:

| Attribute | Kind | Constraint | Purpose |
|---|---|---|---|
| `date_format` | Text | enum: `iso`, `us`, `eu`, `relative` | Display format for dates/datetimes. Final enum list to confirm against existing formatters |
| `branch_delete_mode` | Text | enum: `local`, `local_and_git` | Default selection when opening the branch-delete dialog |
| `show_extra_fields` | Boolean | — | Default for the "show extra attributes/relationships" toggle on object and list views. Final attribute name to align with whatever the UI calls the toggle today |
| `last_used_filters` | JSON | — | Map keyed by schema kind → last-applied filter params. Structure is frontend-owned; backend stores and returns it verbatim |

No attribute is required. A newly-provisioned account has no `CoreUserPreference` node until the frontend writes for the first time.

#### GraphQL operations

A custom pair hides the "lookup account → find preferences → create or update" plumbing and enforces owner-only access in one place. Implemented in `backend/infrahub/graphql/queries/account.py` and `backend/infrahub/graphql/mutations/account.py`, reusing the `AccountMixin` JWT check already in place.

```graphql
query InfrahubMyPreferences {
  InfrahubMyPreferences {
    id
    date_format { value }
    branch_delete_mode { value }
    show_extra_fields { value }
    last_used_filters { value }
  }
}

mutation InfrahubMyPreferencesUpsert($data: CoreUserPreferenceUpsertInput!) {
  InfrahubMyPreferencesUpsert(data: $data) {
    ok
    object {
      id
      date_format { value }
      branch_delete_mode { value }
      show_extra_fields { value }
      last_used_filters { value }
    }
  }
}
```

Upsert semantics: if the caller has no `CoreUserPreference` node, one is created and linked to their account; otherwise the existing node is updated. Each call may set any subset of attributes; unset attributes are left untouched (partial update, not replace).

Standard auto-generated `CoreUserPreferenceCreate/Update/Delete` mutations remain available for admin and SDK use cases; they are not the primary frontend path.

#### Permissions

- The `InfrahubMyPreferences` / `InfrahubMyPreferencesUpsert` operations resolve the account from the JWT and only touch that account's preference node. No path exists through these operations to read or write another user's preferences.
- Administrative reset: an admin with node-level permission on `CoreUserPreference` can delete a user's node via standard GraphQL; the user's next write recreates an empty one. No dedicated reset mutation in V1.

#### Node lifecycle

- **Create:** lazy — first call to `InfrahubMyPreferencesUpsert` creates the node.
- **Read:** `InfrahubMyPreferences` returns `null` when no node exists, so the frontend can render defaults without a special-case 404.
- **Delete:** only via admin path; frontend has no delete operation in V1.
- **Account deletion:** `CoreUserPreference` must be removed when its owning account is deleted (on-delete cascade in the relationship definition).

### Frontend

#### Data layer

- A single TanStack Query hook `useMyPreferences()` in `frontend/app/src/entities/user-preferences/` exposes `{ preferences, updatePreference }`.
- Backed by the `InfrahubMyPreferences` query. Mutation goes through `InfrahubMyPreferencesUpsert` with optimistic cache update + invalidation on error.
- No `localStorage` dual-write; TanStack Query is the sole client-side cache. Authoritative state always lives in the backend.
- Default values are defined client-side and applied when the corresponding attribute is `null`/missing.

#### Call sites (V1)

| Caller | Reads | Writes |
|---|---|---|
| Date formatter helper (`frontend/app/src/shared/hooks/useDateFormat.ts`, new) | `date_format` | — |
| Branch delete button (`frontend/app/src/entities/branches/ui/branch-delete-button.tsx`) | `branch_delete_mode` as default of the mode selector | writes on "remember my choice" |
| Object/list view "show extra fields" toggle | `show_extra_fields` | writes on toggle |
| Object list page filter bar | `last_used_filters[schema_kind]` | writes on filter change (debounced) |

#### Not migrated in V1

- Schema graph visualization state (fold/zoom/positions) stays in `localStorage` for now. A later increment can add a "save view to preferences" action that writes to a new `schema_graph_state` JSON attribute on `CoreUserPreference`. The schema change is additive.

## V2 — Personal Saved Views (planned, not in V1 scope)

### Schema node: `CoreSavedView`

Defined alongside `CoreUserPreference`. Owner-only in V2; sharing added in V3.

| Attribute | Kind | Notes |
|---|---|---|
| `name` | Text | Required, unique per (owner, schema_kind) |
| `description` | Text | Optional |
| `schema_kind` | Text | The kind this view applies to, e.g. `CoreRepository` |
| `filters` | JSON | Filter state, frontend-owned shape |
| `sort` | JSON | Optional sort order |
| `visible_columns` | JSON | Optional column visibility override |

Relationships:

- `owner` → `CoreGenericAccount`, `cardinality=ONE`, required, identifier `account__saved_views`

### Interaction with `CoreUserPreference`

Add one attribute to `CoreUserPreference` in V2:

- `selected_saved_views` (JSON): map `schema_kind → saved_view_id`. Records which view the user currently has active per kind, so reopening the page restores it.

Resolution order when rendering a list page (V2):

1. If `preferences.selected_saved_views[kind]` points to a readable `CoreSavedView`, apply that view's `filters/sort/visible_columns`.
2. Else, apply `preferences.last_used_filters[kind]`.
3. Else, apply the page's built-in defaults.

`last_used_filters` is not touched when a saved view is active. Applying an ad-hoc filter on top of an open saved view is a UX decision deferred to V2 design (see Open Questions).

### GraphQL operations (V2)

Custom owner-scoped query plus standard CRUD mutations:

```graphql
query InfrahubMySavedViews($schema_kind: String) {
  InfrahubMySavedViews(schema_kind: $schema_kind) {
    edges { node { id name description schema_kind filters { value } sort { value } visible_columns { value } } }
  }
}

mutation CoreSavedViewCreate($data: CoreSavedViewCreateInput!) { ... }
mutation CoreSavedViewUpdate($data: CoreSavedViewUpdateInput!) { ... }
mutation CoreSavedViewDelete($data: CoreSavedViewDeleteInput!) { ... }
```

The custom `InfrahubMySavedViews` returns both views owned by the caller and (in V3) views shared with the caller's groups. Standard CRUD is permissioned on ownership.

## V3 — Shared Saved Views (planned, not in V1 scope)

Extend `CoreSavedView` with sharing attributes; no rework of V2 required.

| Addition | Kind | Notes |
|---|---|---|
| `visibility` | Text, enum: `private`, `shared` | Default `private`. Determines whether `shared_with_groups` is consulted |
| `shared_with_groups` | Relationship → `CoreAccountGroup`, `cardinality=MANY` | Members of these groups get read access |

Permission model:

- **Read:** owner always; if `visibility=shared`, any member of `shared_with_groups` as well.
- **Write (update/delete/share):** owner only.
- **Fork:** a read-only viewer can duplicate a shared view into a new `CoreSavedView` owned by them. Implemented as a custom mutation `InfrahubSavedViewFork(id)` that clones attributes and re-parents `owner`.

Sharing is opt-in per view (users don't bulk-share a folder). Groups reuse Infrahub's existing `CoreAccountGroup` model — no new grouping concept is introduced.

Frontend additions (V3): a "Share with groups…" dialog on views the user owns; read-only indication on views shared in; a "Duplicate to my views" action on shared views.

## Out of Scope

- Schema graph visualization state in the backend (deferred; additive schema change when wanted).
- Bulk "reset all preferences to defaults" UI (admin can delete the node).
- Cross-account preference import/export.
- Per-branch preferences (preferences are `AGNOSTIC`; they are not branched).
- Sharing preferences themselves (only saved views will be shareable; preferences remain strictly personal).

## Open Questions

- **Date format enum values.** Final list depends on what the existing frontend formatters already handle. To be resolved during implementation by auditing `frontend/app/src/entities/navigation/ui/time-selector.tsx` and any date-rendering helpers.
- **Extra-fields toggle name.** The attribute should match the UI's wording. To be resolved during implementation by locating the current toggle in object and list views.
- **Debounce window for `last_used_filters` writes.** Suggested starting point: 1 s after the last filter change, with a flush on page navigation.
- **V2 only — ad-hoc edits on top of a saved view.** Behavior when the user changes a filter while a saved view is active: drop the view selection and fall back to `last_used_filters`, or require an explicit "fork / save as" step. Deferred to V2 design.

## Migration & Rollout

- V1 ships purely additive: new schema node, new GraphQL operations, new frontend hook. No data migration required.
- Existing `localStorage`-backed behaviors (schema graph viz) are untouched in V1 and keep working as-is.
- Feature can be released incrementally per call site: date format first (read-only display impact, safe), then branch delete mode, then extra-fields toggle, then list filters.
