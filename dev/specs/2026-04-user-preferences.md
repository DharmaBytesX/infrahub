---
Title: User & Global Preferences
Author:
  - Paul Lemesle
Status: draft
---

# User & Global Preferences

## Summary

Introduce two persistent, schema-backed preference surfaces:

- `CoreGlobalPreference` — admin-defined defaults that apply to every user (one singleton node).
- `CoreUserPreference` — per-user overrides (one node per account).

A single backend-computed query returns the **effective** preferences for the calling user (global merged with their personal overrides), so the frontend never has to merge them itself. Standard auto-generated CRUD mutations are used everywhere; no custom write path.

V1 ships only two attributes — `date_format` and `timezone` — to validate the schema, query, mutation, and UI plumbing end to end. Additional preferences (dark mode, etc.) land in follow-up tickets once the foundation is proven.

Three adjacent concerns get their own spec/ticket and are explicitly **not** part of V1:

- Saved views — `dev/specs/2026-04-saved-views.md`
- Saved filters — `dev/specs/2026-04-saved-filters.md`
- "Show extra fields" toggle persistence — `dev/specs/2026-04-show-extra-fields.md`

## Problem Statement

- UI defaults (date format, timezone) live in component state or the browser's locale. They cannot be set centrally by an organization, and a user's choice does not survive a device switch.
- There is no place for an admin to express "use ISO dates organisation-wide" or "default everyone to UTC".
- There is no schema-backed concept of "preferences" that the SDK or other clients can read.

## Solution Overview

Two schema nodes, one read query that fuses them.

| Node | Cardinality | Who writes | Who reads |
|---|---|---|---|
| `CoreGlobalPreference` | Singleton (0..1) | Admin only | Authenticated users (read effective query) |
| `CoreUserPreference` | One per `CoreGenericAccount` | Owning user (and admin) | Owner (and admin) |

Effective resolution per attribute: **user value if set, else global value, else built-in default**. Defaults live in the frontend (so the SDK sees a `null` for "no opinion stored" and can apply its own).

## Success Criteria — V1

- An admin can set `date_format` and `timezone` once for the organisation; an unauthenticated browser-issued read returns those values for any user without a personal override.
- A user can override either attribute on their own preferences page; the override takes effect on next page load and is visible from any device.
- Removing a user override falls back to the global value; removing the global value falls back to the frontend default.
- Standard CRUD mutations work for both nodes (admin tooling, SDK use, Postman).
- A single GraphQL query returns the effective value to render with — no client-side merging.

## V1 Attributes

Identical attribute set on both nodes (so the merge is trivially per-attribute):

| Attribute | Kind | Notes |
|---|---|---|
| `date_format` | Text | date-fns pattern string (e.g. `dd/MM/yyyy`, `yyyy-MM-dd HH:mm`). Literal `relative` is a sentinel for relative-time rendering. Validated client-side via dry-run `format(new Date(), pattern)`; backend stores verbatim. |
| `timezone` | Text | IANA timezone name (`Europe/Paris`, `UTC`). Validated client-side against `Intl.supportedValuesOf('timeZone')`. Unset = browser-resolved zone. |

All attributes optional on both nodes. Other candidates (dark mode, language, density) are deferred — see "Future preferences" below.

## Backend

### `CoreGlobalPreference`

- Defined in `backend/infrahub/core/schema/definitions/core/account.py` (or `preferences.py` if we prefer to keep account-scoped files focused).
- `name="GlobalPreference"`, `namespace="Core"`.
- `branch=BranchSupportType.AGNOSTIC`.
- Singleton enforced by an empty uniqueness constraint plus a startup check that creates the row if missing — or, simpler, treated as "0..1, app code refuses to create a second one". Decision flagged for implementation.
- No relationships in V1.

```yaml
- name: GlobalPreference
  namespace: Core
  label: Global Preference
  description: Organisation-wide defaults applied to every user unless overridden.
  branch: agnostic
  include_in_menu: false
  generate_profile: false
  display_label: "Global Preferences"
  icon: mdi:cog
  attributes:
    - name: date_format
      kind: Text
      optional: true
      order_weight: 1000
    - name: timezone
      kind: Text
      optional: true
      order_weight: 1100
```

### `CoreUserPreference`

- Same file as above. Same V1 attribute set as `CoreGlobalPreference`.
- Relationship `account` → `CoreGenericAccount`, cardinality ONE, required, identifier `account__preferences`, `on_delete: cascade`.
- Uniqueness constraint on `account` so an account has at most one preference node.

```yaml
- name: UserPreference
  namespace: Core
  label: User Preference
  description: Per-user overrides of global preferences.
  branch: agnostic
  include_in_menu: false
  generate_profile: false
  display_label: "Preferences of {{ account__name__value }}"
  icon: mdi:account-cog-outline
  uniqueness_constraints:
    - ["account"]
  attributes:
    - name: date_format
      kind: Text
      optional: true
      order_weight: 1000
    - name: timezone
      kind: Text
      optional: true
      order_weight: 1100
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

### GraphQL operations

**Standard auto-generated mutations** are the primary write path:

- `CoreGlobalPreferenceUpsert / Update / Delete` — admin only via permissions.
- `CoreUserPreferenceUpsert / Update / Delete` — node-level permission scoped to owner-or-admin.

No custom write mutation — keeps the surface predictable and aligned with the rest of the schema.

**Standard auto-generated queries** are also exposed (`CoreGlobalPreference`, `CoreUserPreference`) for admin tooling and SDK introspection.

**One custom read query** for the rendering path:

```graphql
query InfrahubEffectivePreferences {
  InfrahubEffectivePreferences {
    date_format   # value or null
    timezone      # value or null
    # scalar fields, not Attribute wrappers — this is a computed view, not a node
  }
}
```

Implementation in `backend/infrahub/graphql/queries/preferences.py`:

1. Resolve account from JWT (existing `AccountMixin` pattern).
2. Read the singleton `CoreGlobalPreference` (cache-friendly, branch-agnostic).
3. Read the caller's `CoreUserPreference` if any.
4. Per attribute: return user value if set, else global value, else `null`.

The frontend interprets `null` as "use built-in default". The SDK can do the same.

### Permissions

| Operation | Allowed for |
|---|---|
| Read `InfrahubEffectivePreferences` | Any authenticated account (returns their own effective view) |
| Read `CoreGlobalPreference` | Any authenticated account |
| Write `CoreGlobalPreference` | Admins (via existing node-level permission model) |
| Read/write `CoreUserPreference` | Owner; admin can also read/write any user's prefs |

Owner check on `CoreUserPreference` writes is enforced through the standard permission system, not bespoke logic — same approach as `AccountToken`.

## Frontend

### Data layer

- TanStack Query hook `useEffectivePreferences()` in `frontend/app/src/entities/preferences/` exposes `{ date_format, timezone }` (already merged).
- Hooks for admin paths: `useGlobalPreferences()` / `useUpdateGlobalPreferences()`.
- Hooks for the user override path: `useMyUserPreferences()` / `useUpdateMyUserPreferences()`.
- All write hooks invalidate `useEffectivePreferences()` on success.
- No `localStorage` dual-write.

### Preferences page

New route `/settings/preferences` (exact path TBD against existing settings IA):

- Two sections, only visible if the user has the relevant permission:
  - **My preferences** — editable form for `date_format`, `timezone`. Each field shows the inherited global value as its placeholder/hint when the user has no override; a "reset to global" button clears the override.
  - **Organisation defaults** *(admin only)* — editable form for the same fields on `CoreGlobalPreference`.
- Form validation:
  - `date_format`: dry-run `date-fns.format(new Date(), value)`; reject if it throws.
  - `timezone`: must be in `Intl.supportedValuesOf('timeZone')`.

### Date formatter helper

`frontend/app/src/shared/hooks/useDateFormat.ts` (new):

- Reads `useEffectivePreferences()`.
- Default `date_format` if both global and user are unset: `yyyy-MM-dd HH:mm` (decision flagged).
- Default `timezone` if unset: `Intl.DateTimeFormat().resolvedOptions().timeZone`.
- Routes through `date-fns` + `date-fns-tz` (~15 kB gz, new dependency).
- All current `format(date, …)` call sites migrate to this helper so the preference applies uniformly.

## Future Preferences (out of V1, listed for context)

These will be added incrementally once the V1 plumbing is proven. Each requires its own design pass:

- **Dark mode / theme** — needs a decision on system-vs-stored preference, transition strategy, and whether the global default is meaningful.
- **Language** — depends on the i18n strategy.
- **Density** (compact / comfortable list rows).
- **Default landing page after login**.

These are listed here as a backlog hint, not committed scope.

## Out of Scope (separate specs/tickets)

- Saved views — `dev/specs/2026-04-saved-views.md`
- Saved filters (formerly `last_used_filters`) — `dev/specs/2026-04-saved-filters.md`
- "Show extra fields" toggle persistence — `dev/specs/2026-04-show-extra-fields.md`
- `branch_delete_mode` — explicitly dropped. Persisting a destructive default is too dangerous; the dialog will keep prompting per action.
- Cross-account preference import/export.
- Schema graph visualisation state (fold/zoom/positions) — stays in `localStorage` for now.

## Open Questions

- **Singleton enforcement for `CoreGlobalPreference`.** Easiest is "treat as 0..1, app refuses to create a second", possibly seeded by a migration creating an empty row. Confirm during implementation.
- **Effective query shape.** Returning scalar fields rather than the standard `Attribute { value }` wrapper diverges from the rest of the GraphQL surface. Tradeoff: easier to consume, but inconsistent. Open for review.
- **Default `date_format` when nothing is stored.** Suggested: `yyyy-MM-dd HH:mm`. Locale-aware default would be friendlier but couples behaviour to browser locale and hides the inheritance chain.
- **Settings page location.** Slot under existing account settings, or top-level `/settings/preferences`?

## Migration & Rollout

- Purely additive. New schema nodes, new GraphQL query, new frontend hook + page.
- Existing date-rendering code keeps working until each call site migrates to the new helper. Migration can ship incrementally per call site.
- No data migration required.
