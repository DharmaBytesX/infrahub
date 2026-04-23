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

## Success Criteria

### V1

- Users can set date format, branch-delete default, extra-fields toggle, and filter defaults once and have them persist across devices.
- Users can remove their preferences to reset to defaults.

### V2

- Users can save ≥1 named view per schema kind and switch between them.
- Schema graph visualization state is persisted in the backend.

### V3

- A user can share a view with a group and another group member can open it read-only.

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
| `date_format` | Text | — | Free-form display format for dates/datetimes, stored as a date-fns pattern string (e.g. `dd/MM/yyyy`, `yyyy-MM-dd HH:mm`). The settings UI offers common patterns as presets (`yyyy-MM-dd`, `dd/MM/yyyy`, `MM/dd/yyyy`, `dd.MM.yyyy`, `PP`, `relative`) but the stored value is always the raw pattern. The literal string `relative` is a sentinel handled by the formatter (renders "2 hours ago"–style output) and is the only non-date-fns value accepted |
| `timezone` | Text | — | IANA timezone name (e.g. `Europe/Paris`, `UTC`). Unset means "use the browser's resolved timezone". Not an enum — the IANA set is ~400 entries and grows; the frontend validates input against `Intl.supportedValuesOf('timeZone')` before submit |
| `branch_delete_mode` | Text | enum: `local`, `local_and_git` | Default selection when opening the branch-delete dialog |
| `show_extra_fields` | Boolean | — | Default for the "show extra attributes/relationships" toggle on object and list views. Final attribute name to align with whatever the UI calls the toggle today |
| `last_used_filters` | JSON | — | Map keyed by schema kind → last-applied filter params. Structure is frontend-owned; backend stores and returns it verbatim |

No attribute is required. A newly-provisioned account has no `CoreUserPreference` node until the frontend writes for the first time.

YAML shape (reference; authoritative source is the Python definition in `account.py`):

```yaml
# yaml-language-server: $schema=https://schema.infrahub.app/infrahub/schema/latest.json
version: "1.0"
nodes:
  - name: UserPreference
    namespace: Core
    label: User Preference
    description: Per-user UI defaults and implicit state (one per account).
    branch: agnostic
    include_in_menu: false
    generate_profile: false
    display_label: "Preferences of {{ account__name__value }}"
    icon: mdi:cog-outline
    uniqueness_constraints:
      - ["account"]
    attributes:
      - name: date_format
        kind: Text
        optional: true
        order_weight: 1000
        description: >-
          Free-form date-fns pattern string (e.g. "dd/MM/yyyy",
          "yyyy-MM-dd HH:mm"). The literal "relative" is a sentinel for
          relative-time rendering ("2 hours ago"); all other values are
          passed to date-fns format() verbatim.
      - name: timezone
        kind: Text
        optional: true
        order_weight: 1050
        description: >-
          IANA timezone name (e.g. Europe/Paris, UTC). Unset means
          "use the browser's resolved timezone". Not an enum — the frontend
          validates input against Intl.supportedValuesOf('timeZone').
      - name: branch_delete_mode
        kind: Text
        enum: [local, local_and_git]
        optional: true
        order_weight: 1100
        description: Default selection in the branch-delete dialog.
      - name: show_extra_fields
        kind: Boolean
        optional: true
        order_weight: 1200
        description: Default for the "show extra fields" toggle on object/list views.
      - name: last_used_filters
        kind: JSON
        optional: true
        order_weight: 1300
        description: Frontend-owned map, schema_kind -> last applied filter params.
    relationships:
      - name: account
        peer: CoreGenericAccount
        identifier: account__preferences
        kind: Parent
        cardinality: one
        optional: false
        on_delete: cascade
        order_weight: 100
```

#### GraphQL operations

A custom pair hides the "lookup account → find preferences → create or update" plumbing and enforces owner-only access in one place. Implemented in `backend/infrahub/graphql/queries/account.py` and `backend/infrahub/graphql/mutations/account.py`, reusing the `AccountMixin` JWT check already in place.

```graphql
query InfrahubMyPreferences {
  InfrahubMyPreferences {
    id
    date_format { value }
    timezone { value }
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
      timezone { value }
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
| Date formatter helper (`frontend/app/src/shared/hooks/useDateFormat.ts`, new) | `date_format`, `timezone` | — |
| Branch delete button (`frontend/app/src/entities/branches/ui/branch-delete-button.tsx`) | `branch_delete_mode` as default of the mode selector | writes on "remember my choice" |
| Object/list view "show extra fields" toggle | `show_extra_fields` | writes on toggle |
| Object list page filter bar | `last_used_filters[schema_kind]` | writes on filter change (debounced) |

The date formatter helper passes `date_format` straight to date-fns `format()` (short-circuiting to `formatDistanceToNow` when the value is `relative`), and applies `timezone` via `date-fns-tz` (new dependency, ~15 kB gz). All existing `format(date, …)` call sites route through this helper so preferences apply uniformly. When `timezone` is unset, the helper uses `Intl.DateTimeFormat().resolvedOptions().timeZone`. Invalid patterns are caught client-side at write time (settings form validates by attempting a dry-run `format(new Date(), pattern)`); the backend does not validate date-fns syntax.

#### Not migrated in V1

- Schema graph visualization state (fold/zoom/positions) stays in `localStorage` for V1. V2 moves it to the backend via an additive `schema_graph_state` JSON attribute on `CoreUserPreference`.

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

YAML shape (V2, owner-only; V3 extensions in the next section):

```yaml
# yaml-language-server: $schema=https://schema.infrahub.app/infrahub/schema/latest.json
version: "1.0"
nodes:
  - name: SavedView
    namespace: Core
    label: Saved View
    description: Named filter/sort/column preset for a schema kind.
    branch: agnostic
    default_filter: name__value
    order_by: [schema_kind__value, name__value]
    human_friendly_id: ["owner__name__value", "schema_kind__value", "name__value"]
    display_label: "{{ name__value }} ({{ schema_kind__value }})"
    icon: mdi:bookmark-outline
    include_in_menu: false
    uniqueness_constraints:
      - ["owner", "schema_kind__value", "name__value"]
    attributes:
      - name: name
        kind: Text
        optional: false
        order_weight: 1000
      - name: description
        kind: Text
        optional: true
        order_weight: 1100
      - name: schema_kind
        kind: Text
        optional: false
        order_weight: 1200
      - name: filters
        kind: JSON
        optional: true
        order_weight: 2000
      - name: sort
        kind: JSON
        optional: true
        order_weight: 2100
      - name: visible_columns
        kind: JSON
        optional: true
        order_weight: 2200
    relationships:
      - name: owner
        peer: CoreGenericAccount
        identifier: account__saved_views
        kind: Parent
        cardinality: one
        optional: false
        on_delete: cascade
        order_weight: 100
```

### Interaction with `CoreUserPreference`

Add two attributes to `CoreUserPreference` in V2:

- `selected_saved_views` (JSON): map `schema_kind → saved_view_id`. Records which view the user currently has active per kind, so reopening the page restores it.
- `schema_graph_state` (JSON): fold/zoom/positions and any other per-user schema graph visualization state, migrated off `localStorage`.

YAML diff (additive — the V1 block above gains these two attributes):

```yaml
# additions to CoreUserPreference.attributes in V2
- name: selected_saved_views
  kind: JSON
  optional: true
  order_weight: 1400
  description: Map schema_kind -> saved_view_id currently active.
- name: schema_graph_state
  kind: JSON
  optional: true
  order_weight: 1500
  description: Fold/zoom/positions of the schema graph visualization.
```

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

Extend `CoreSavedView` with two sharing relationships; no rework of V2 required.

| Addition | Kind | Notes |
|---|---|---|
| `shared_with_groups` | Relationship → `CoreAccountGroup`, `cardinality=MANY` | Members of these groups get read access |
| `shared_with_accounts` | Relationship → `CoreGenericAccount`, `cardinality=MANY` | Direct share with specific users, no group required |

No `visibility` enum: a view is private iff both share relationships are empty. Single source of truth, and "unshare" is just removing the peer. Sharing remains opt-in per view — there is no bulk folder-level share concept.

YAML diff (additive — appended to `CoreSavedView.relationships` from V2):

```yaml
# additions to CoreSavedView.relationships in V3
- name: shared_with_groups
  peer: CoreAccountGroup
  identifier: saved_view__shared_groups
  kind: Attribute
  cardinality: many
  optional: true
  order_weight: 3000
  description: Members of these groups get read access.
- name: shared_with_accounts
  peer: CoreGenericAccount
  identifier: saved_view__shared_accounts
  kind: Attribute
  cardinality: many
  optional: true
  order_weight: 3100
  description: Direct share with specific users.
```


Permission model:

- **Read:** owner always; any account in `shared_with_accounts`; any account that is a member of a group in `shared_with_groups`. Resolved as a single one-hop graph predicate (`account -[:member_of]-> group <-[:shared_with_groups]- view` ∪ `account <-[:shared_with_accounts]- view`), reusing how `CoreAccountGroup.members` is already traversed in `backend/infrahub/auth.py`.
- **Write (update/delete/share):** owner only.
- **Fork:** a read-only viewer can duplicate a shared view into a new `CoreSavedView` owned by them. Implemented as a custom mutation `InfrahubSavedViewFork(id)` that clones attributes and re-parents `owner`. No native primitive replaces this.

Groups reuse Infrahub's existing `CoreAccountGroup` model — no new grouping concept is introduced.

Frontend additions (V3): a "Share…" dialog on views the user owns (targets groups and/or users); read-only indication on views shared in; a "Duplicate to my views" action on shared views.

## Out of Scope

- Cross-account preference import/export.

## Open Questions

- **Date format storage.** Resolved: store the raw date-fns pattern as free-form text (no enum). The settings UI exposes a handful of presets for discoverability, but the stored value is always the pattern itself so users can enter any combination (`dd/MM/yyyy HH:mm`, `yyyy-MM-dd`, etc.) without a schema change. The literal `relative` is reserved as a sentinel for relative-time rendering. Tradeoff accepted: stored values are coupled to date-fns token syntax; swapping formatter libraries later would require a data migration. Validation lives on the client (attempt a dry-run format); the backend stores what it receives.
- **Timezone override.** Resolved: add a separate `timezone` Text attribute (IANA name, optional, unset = browser local). Conflating it with `date_format` would mix appearance with semantic value. Adopting zone-aware formatting requires `date-fns-tz` as a new frontend dependency (~15 kB gz) since plain `date-fns` does not convert zones — flag during implementation.
- **Extra-fields toggle name.** The attribute should match the UI's wording. To be resolved during implementation by locating the current toggle in object and list views.
- **Debounce window for `last_used_filters` writes.** Suggested starting point: 1 s after the last filter change, with a flush on page navigation.
- **V2 only — ad-hoc edits on top of a saved view.** Behavior when the user changes a filter while a saved view is active: drop the view selection and fall back to `last_used_filters`, or require an explicit "fork / save as" step. Deferred to V2 design.
- **V3 only — reuse `LINEAGEOWNER` for `CoreSavedView.owner`.** `CoreRepository`, `CoreAccount`, and others already inherit Infrahub's `LINEAGEOWNER` generic for audit trail. If `CoreSavedView` inherits it, the custom `owner` relationship can be dropped and "created by" comes for free — but only if write authorization can key off the lineage owner cleanly. Needs verification before committing.

## Migration & Rollout

- V1 ships purely additive: new schema node, new GraphQL operations, new frontend hook. No data migration required.
- Existing `localStorage`-backed behaviors (schema graph viz) are untouched in V1 and keep working as-is.
- Feature can be released incrementally per call site: date format first (read-only display impact, safe), then branch delete mode, then extra-fields toggle, then list filters.
