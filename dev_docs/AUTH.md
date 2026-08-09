# Peach 1UP: Auth System Reference

Complete map of every auth flow, token/cookie lifecycle, permission model, CORS, and
middleware chain. Read alongside [SECURITY.md](SECURITY.md) (policy rules) and
[TECH.md](TECH.md) (stack).

---

## Directory / File Index

| Path | Purpose |
|------|---------|
| [`backend/main.py`](../backend/main.py) | Mounts all routers; sets middleware order (RequestLogging → CORS → Security → CSRF → FirstRunGuard → router) |
| [`backend/api/middleware/security.py`](../backend/api/middleware/security.py) | `SecurityMiddleware` (localhost enforcement, X-Request-ID), `CSRFMiddleware` (double-submit cookie), `FirstRunGuardMiddleware` (redirect to /first-run), CORS config |
| [`backend/api/middleware/request_logging.py`](../backend/api/middleware/request_logging.py) | `RequestLoggingMiddleware`: logs method, path, status, and duration only. No headers or bodies are logged |
| [`backend/api/routes/auth.py`](../backend/api/routes/auth.py) | `/api/v1/auth`: setup-owner, switch, logout, me, refresh |
| [`backend/api/routes/users.py`](../backend/api/routes/users.py) | `/api/v1/users`: CRUD users, reset-pin, unlock, force-logout. `GET /api/v1/users` (list) is intentionally unauthenticated, see the dedicated section below |
| [`backend/api/routes/settings.py`](../backend/api/routes/settings.py) | `/api/v1/settings`: first-run-status, complete-first-run, patch settings, pin-pepper |
| [`backend/core/dependencies.py`](../backend/core/dependencies.py) | `get_active_user`, `require_permission`, `require_self_or_admin`, `require_admin_or_self_manage`, `require_owner_or_admin`, `require_game_or_environment_editor`, and the `get_filtered_*` collection filters |
| [`backend/core/identity.py`](../backend/core/identity.py) | `generate_identity_secret`, `mint_session_token`, `hash_session_token`, `issue_session`, `extend_session`, `clear_session`, `validate_session`, `parse_session_cookie`. HMAC-derived session tokens, no separate token table |
| [`backend/core/rate_limit.py`](../backend/core/rate_limit.py) | `check_and_record` / `enforce`: in-memory sliding-window IP rate limiter used by `/auth/switch` |
| [`backend/models/user.py`](../backend/models/user.py) | `UserItem` DB model, `UserItemBase` field base, `UserItemRead` response schema. Carries `identity_token_secret`, `session_token_hash`, `session_token_expires_at`, `session_token_ttl` |
| [`backend/models/media_restriction.py`](../backend/models/media_restriction.py) | `MediaRestriction`: per-user item block list, table `restrictions` |
| [`backend/core/lifespan.py`](../backend/core/lifespan.py) | Startup: DB init, first-run flag sync, owner-exists check |
| [`scripts/setup_admin_user.py`](../scripts/setup_admin_user.py) | CLI emergency owner reset (bypasses web, writes DB directly) |
| [`frontend/src/api/client.ts`](../frontend/src/api/client.ts) | `ApiClient`: all requests, `credentials: "include"`, `X-CSRF-Token` header on mutating requests, session-expired event dispatch |
| [`frontend/src/context/AppContext.tsx`](../frontend/src/context/AppContext.tsx) | Mounts provider; calls `GET /auth/me` on load then `POST /auth/refresh` to extend the session; `useRef` guard prevents the mount effect's `/auth/me` → `/auth/refresh` chain from double-firing under StrictMode; listens for `session-expired` event |
| [`frontend/src/context/_AppContext.ts`](../frontend/src/context/_AppContext.ts) | `AppState`, `AppAction`, `appReducer`: `activeUser`, `showUnauthModal` |
| [`frontend/src/pages/FirstRun/index.tsx`](../frontend/src/pages/FirstRun/index.tsx) | Wizard shell; polls first-run-status; calls complete-first-run |
| [`frontend/src/pages/FirstRun/Step0Owner.tsx`](../frontend/src/pages/FirstRun/Step0Owner.tsx) | Form that calls `POST /auth/setup-owner` and sets `activeUser` |
| [`frontend/src/components/UserSwitcher.tsx`](../frontend/src/components/UserSwitcher.tsx) | User-switch UI; PIN modal; calls `POST /auth/switch` |
| [`frontend/src/components/layout/AppShell.tsx`](../frontend/src/components/layout/AppShell.tsx) | Shows signed-out banner on `showUnauthModal`; navigates to `/users` (the standalone switch-account page) when unauthenticated |
| [`frontend/src/pages/Users/index.tsx`](../frontend/src/pages/Users/index.tsx) | Standalone Users/switch-account page (moved out of Settings). Lists accounts via unauthenticated `GET /api/v1/users`, owner-only create/delete controls, admin-only edit/reset-pin/unlock controls |

---

## Token & Cookie Model

| Property | Value |
|----------|-------|
| Session cookie name | `peach_token` |
| Session cookie flags | `HttpOnly`, `SameSite=Lax`. `Secure` follows `ALLOW_NETWORK_ACCESS`: `False` while it is off (default, localhost only), `True` once it is set to `true`. With `Secure=True` and no TLS-terminating reverse proxy in front of the service, browsers silently drop the cookie over plain HTTP. Login appears to succeed but every subsequent request looks unauthenticated, producing an infinite re-login loop with no error shown (see [SECURITY.md](SECURITY.md) § Network Rules) |
| CSRF cookie name | `peach_csrf` |
| CSRF cookie flags | **Not** HttpOnly (JS-readable), `SameSite=Lax`, `Secure` follows `ALLOW_NETWORK_ACCESS` the same way as the session cookie; same `max_age` as the session cookie |
| Cookie `max_age` | `session_token_ttl * 60` seconds when a TTL is set, otherwise a fixed 30 days. The browser-side lifetime is therefore bounded even when the server-side session never expires |
| CSRF enforcement | `CSRFMiddleware`: all state-mutating requests must send an `X-CSRF-Token` header matching the `peach_csrf` value. Auth endpoints (`/api/v1/auth/*`) are exempt |
| Token storage | Columns on the `UserItem` row: `identity_token_secret`, `session_token_hash`, `session_token_expires_at`, `session_token_ttl`. No separate table |
| Token value | `mint_session_token(identity_token_secret)` → HMAC-SHA256(`identity_token_secret`, `nonce + "." + issued_at.isoformat()`), hex digest. Cookie stores `{user_item_id}.{session_token}`; only `hash_session_token()` (plain SHA-256) of the token is persisted |
| Default expiry | No server-side expiry (`session_token_expires_at = NULL`) unless `UserItem.session_token_ttl` (minutes) is set |
| Multiple sessions | Not allowed, one active session per user by design. `issue_session()` overwrites `session_token_hash` directly, so a new login invalidates any prior session. Used only by `/auth/setup-owner` and `/auth/switch`, never by `/auth/refresh` |
| Session extension | `extend_session(db, user)` recomputes `session_token_expires_at` from `session_token_ttl` only. It never touches `session_token_hash` and never mints a new token, so `/auth/refresh` is idempotent across concurrent calls (StrictMode double-mount, multiple tabs, retries). The old rotate-on-refresh design 401'd the second of two near-simultaneous refresh calls because the first overwrote the hash the second was still presenting |
| Revocation | `clear_session()` nulls `session_token_hash` and `session_token_expires_at` on the user row. Used by `/auth/logout` and `POST /users/{id}/force-logout`; there is no row to delete |
| Session validation | `validate_session(db, user_item_id, token)` returns None if the user is missing, if `session_token_hash` is `NULL` (logged out), or if `session_token_expires_at` has passed, then compares the hash against the presented token with `hmac.compare_digest` |
| Expired/revoked cleanup | None needed. Expiry and revocation are point-in-time checks against the single hash column, not a cleanup job |
| Frontend sends cookie | Every request, via `credentials: "include"` in `ApiClient.fetch` |
| Frontend sends CSRF | `ApiClient.fetch` reads `peach_csrf` from `document.cookie` and adds the `X-CSRF-Token` header on all non-GET/HEAD/OPTIONS requests |

---

## Permission Flags

The authoritative list is `UserItemBase` in
[`backend/models/user.py`](../backend/models/user.py); this table must be kept in step
with it.

| Flag | Default for owner | Default for sub-account | What it gates |
|------|:-:|:-:|------|
| `is_owner` | `True` | always `False` | Bypasses all `require_permission` checks. Also used directly as the gating flag on create/delete sub-account (see Flow 9, Flow 13) |
| `is_admin` | `True` | `False` | Gates endpoints that check `is_admin` directly: edit/reset-pin/unlock/force-logout sub-account, plus various admin-only settings/emulator/BIOS endpoints. Grants no other `can_*` flag implicitly; `require_permission()` special-cases only `is_owner` for bypass, and every other flag (including `is_admin` itself) is checked independently via `getattr(active_user, flag, False)`. On `reset-pin` an admin may target only regular/capped sub-accounts: the owner and every admin (including the caller's own record) are rejected with 403, and only the owner may reset an admin's PIN |
| `can_launch_media` | `True` | `True` | Launch any permitted software collection |
| `can_manage_game` | `True` | `False` | Add/edit/delete software collections and items and their drives, run `POST /software/scan` and import-from-path, **and** create/modify/delete launch Profiles ([`routes/profiles.py`](../backend/api/routes/profiles.py)). Was `can_edit_library` → `can_edit_software` → this name |
| `can_manage_environment` | `True` | `False` | Register/modify Environments (Windows OS install workspaces). Was `can_edit_platforms` |
| `can_manage_media` | `True` | `False` | Add/edit/delete Media (the archival audio/text/image/video domain) |
| `can_manage_app` | `True` | `False` | Add/edit/delete Apps (the `AppItemBundle` domain) and gates the app-upload router |
| `can_manage_controllerMapping` | `True` | `False` | Create/edit/delete controller mappings (System → Controllers) |
| `can_manage_settings` | `True` | `False` | Modify application settings |
| `can_manage_users` | `False` (irrelevant, owner bypasses) | `False` | Lets a sub-account edit **its own** `name` via `PATCH /users/{id}` and reset **its own** PIN via `POST /users/{id}/reset-pin`, nothing else. Grants no capability over any other user's account, no delete, and none of the owner-only create/delete-sub-account operations. Owner-only to grant, like every permission flag. Gated by `require_admin_or_self_manage`, checked in addition to (not instead of) the existing `is_admin`-targets-others path on those two endpoints |

`setup_owner` sets every flag above except `can_manage_users`, which stays at its `False`
default because the owner bypasses `require_permission` regardless.

`require_permission(flag)` in `dependencies.py`: the owner bypasses unconditionally,
everyone else must have the literal boolean flag set. Returns 403 on failure.

### ACL Decision Tree

```mermaid
flowchart TD
    A[Request arrives with peach_token cookie] --> B{Cookie present?}
    B -- No --> Z401[401 Not authenticated]
    B -- Yes --> C{parse_session_cookie\nsplits user_item_id.token?}
    C -- No / malformed --> Z401
    C -- Yes --> D{validate_session:\nuser exists AND\nsession_token_hash not NULL AND\nnot expired AND\nhmac.compare_digest matches?}
    D -- No --> Z401b[401 Invalid or expired session]
    D -- Yes --> E[active_user resolved]

    E --> F{require_permission flag}
    F --> G{active_user.is_owner?}
    G -- Yes --> PASS1[Pass, owner bypasses every\nrequire_permission check]
    G -- No --> H["getattr(active_user, flag, False)\nflag is literal: can_manage_game,\ncan_manage_environment, can_manage_media,\ncan_manage_app, can_manage_controllerMapping,\ncan_manage_settings, can_launch_media,\nis_admin, or is_owner"]
    H -- True --> PASS2[Pass]
    H -- False --> Z403[403 Permission denied: requires flag\nis_admin grants no other flag implicitly]

    E --> S{"POST /users (create)\nor DELETE /users/id (delete)"}
    S --> SG{require_permission\n'is_owner'}
    SG -- "active_user.is_owner == False" --> Z403b["403 owner-only,\nadmin sub-accounts cannot\ncreate or delete sub-accounts"]
    SG -- "active_user.is_owner == True" --> SPASS[Pass]

    E --> T{"PATCH /users/id\nor reset-pin"}
    T --> TG{require_admin_or_self_manage}
    TG --> TG1{"active_user.is_owner\nOR active_user.is_admin?"}
    TG1 -- Yes --> TO{target user.is_owner?}
    TG1 -- No --> TG2{"active_user.id == path user_item_id\nAND active_user.can_manage_users?"}
    TG2 -- No --> Z403e[403 Permission denied]
    TG2 -- Yes --> TO
    TO -- Yes --> Z403d[403 Owner account\ncannot be modified here]
    TO -- No --> TAR{"reset-pin AND\ntarget user.is_admin AND\nactive_user not owner?"}
    TAR -- Yes --> Z403h["403 Only the owner\ncan reset an admin's PIN"]
    TAR -- No --> TRP{"reset-pin AND\ntarget user.is_locked AND\nactive_user not owner/admin?"}
    TRP -- Yes --> Z403g["403 Account is locked;\nan admin must reset this PIN\n(self-reset unavailable regardless\nof can_manage_users)"]
    TRP -- No --> TO2{"Caller is owner/admin\nediting via PATCH?"}
    TO2 -- Yes --> TPASS[Pass, full UserPatch applied]
    TO2 -- No --> TF{"Self-edit via\ncan_manage_users only\nbody fields besides name?"}
    TF -- Yes --> Z403f["403 Self-edit may only\nchange name"]
    TF -- No --> TPASS2["Pass, name only\n(or reset-pin: PIN only,\nno field restriction needed)"]

    E --> U{"unlock, force-logout"}
    U --> UG{require_permission 'is_admin'}
    UG -- fail --> Z403c[403]
    UG -- pass --> UO{target user.is_owner?}
    UO -- Yes --> Z403d
    UO -- No --> UPASS[Pass]
```

---

## Middleware Chain (LIFO, last-added runs first)

```text
Browser request
  → RequestLoggingMiddleware : logs method, path, status, duration. Never logs headers or bodies
  → CORSMiddleware          : preflight handling; allow_origins defaults to ["http://localhost:5173"] + optional CORS_ORIGIN env
  → SecurityMiddleware      : reject non-localhost clients when ALLOW_NETWORK_ACCESS=false; inject X-Request-ID
  → CSRFMiddleware          : double-submit cookie check for state-mutating requests; exempt: safe methods, /api/v1/auth/* endpoints, requests with no session cookie
  → FirstRunGuardMiddleware : redirect non-API, non-asset, non /first-run paths to /first-run when first_run_complete is false
  → Router / Handler
```

CORS origins: `http://localhost:5173` is always included; the `CORS_ORIGIN` env var adds
one override. `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.

`FirstRunGuardMiddleware` reads `_first_run_done_cache`, an in-memory bool set at startup
from the DB and again when `complete-first-run` is called. No DB query per request.

`CSRFMiddleware` skips the check entirely when no `peach_token` cookie is present, so
unauthenticated callers get a 401 from the auth dependency rather than a misleading 403.

OPTIONS requests bypass both `SecurityMiddleware` and `FirstRunGuardMiddleware`.

---

## Flow 1: First Launch (no owner, no DB)

```text
App starts
  → lifespan: init DB, create tables, run migrations
  → _sync_first_run_from_db → first_run_complete = false → _first_run_done_cache = false
  → _ensure_owner_user → no owner → logs warning "Complete the first-run setup"
  → FirstRunGuardMiddleware active

Browser opens http://localhost:8000/
  → SecurityMiddleware: client=localhost → pass
  → FirstRunGuardMiddleware: first_run_complete=false, path="/" → redirect /first-run

Browser loads /first-run
  → GET /api/v1/settings/first-run-status (unauthenticated, API path bypasses guard)
    → returns { first_run_complete: false, owner_exists: false }
  → FirstRun page renders Step0Owner form

User fills name + PIN + confirm PIN → clicks "Create Account"
  → POST /api/v1/auth/setup-owner
    → pre-check: no existing owner. The real guarantee is the idx_single_owner partial
      unique index; a lost race raises IntegrityError and is mapped to the same 409
    → validate: name non-empty, PIN 4-6 digits, PINs match
    → Argon2id hash PIN → create UserItem(is_owner=true, is_admin=true, pin_required=true,
      all can_* flags except can_manage_users = true,
      identity_token_secret=generate_identity_secret())
    → issue_session(db, owner) → mint HMAC session token, store its hash on the user row
    → Set-Cookie: peach_token=<user_item_id>.<token>; HttpOnly; SameSite=Lax
    → Set-Cookie: peach_csrf=<random>; SameSite=Lax (JS-readable)
    → return { user: UserItemRead }
  → Frontend: dispatch SET_ACTIVE_USER
  → Frontend: call POST /api/v1/settings/complete-first-run
    → require_permission("can_manage_settings") → owner → pass
    → write settings row first_run_complete="true"
    → set_first_run_complete() → _first_run_done_cache = true
  → Frontend: window.location.replace("/") → full reload → redirect to /software
```

---

## Flow 2: Normal App Boot (owner exists, session may exist)

```text
App starts
  → lifespan: DB ready, first_run_complete=true → _first_run_done_cache=true
  → FirstRunGuardMiddleware inactive (passthrough)

Browser opens app
  → AppProvider mounts → calls GET /api/v1/auth/me
    → cookie peach_token present?
      → YES → parse_session_cookie splits it into (user_item_id, token); validate_session
               checks session_token_hash matches and is not expired → return UserItem
               → dispatch SET_ACTIVE_USER (also clears showUnauthModal)
               → then calls POST /api/v1/auth/refresh (non-fatal)
                 → extend_session pushes out session_token_expires_at only: same
                   token, same session_token_hash, no rotation
                 → peach_token cookie re-set with the same token value and a refreshed
                   max_age only if session_token_ttl is set; peach_csrf always re-set
                 → dispatch SET_ACTIVE_USER with refreshed user
      → NO  → 401 → dispatch LOGOUT → showUnauthModal=true
```

A `useRef` guard in AppProvider's mount effect ensures this `/auth/me` → `/auth/refresh`
chain fires only once per mount, even under React StrictMode's double-invoke in dev.

---

## Flow 3: Session Expiry / Token Invalid Mid-Session

```text
Any API call with a cookie that fails validation (no hash set, expired, or token mismatch)
  → Backend: validate_session returns None → 401 Unauthorized

ApiClient.fetch receives 401
  → isSessionError = true
  → dispatch CustomEvent("session-expired")

AppProvider listener fires
  → dispatch LOGOUT → activeUser=null, showUnauthModal=true

AppShell detects showUnauthModal=true
  → navigate("/users")
  → renders signed-out banner "You have been signed out. Please sign in to continue."

User clicks another account in UserSwitcher → PIN modal → POST /auth/switch → new token issued
```

---

## Flow 4: User Switch (owner account)

```text
UserSwitcher: user clicks owner card (always requires PIN even if already active)
  → setPinTarget(owner)

PinModal renders → user enters PIN → form submit
  → POST /api/v1/auth/switch { user_item_id: <owner_id>, pin: "<pin>" }
    → rate_limit.check_and_record("auth-switch:<client ip>", 30, 60s)
      → over budget → 429 with Retry-After. Keyed on the immediate TCP peer, never
        X-Forwarded-For, which is attacker-controlled without a trusted proxy
    → fetch user by id
    → user.is_locked? → 403
    → user.is_owner=true → require non-empty PIN
    → _verify_pin(pin, pin_hash)
      → FAIL → _record_failed_pin_attempt (single atomic UPDATE) → locks at >= 4 → 401
      → PASS → failed_pin_attempts=0 → issue_session → Set-Cookie (peach_token, peach_csrf) → return user
  → dispatch SET_ACTIVE_USER(owner)
  → queryClient.invalidateQueries(["library"]) re-fetches the filtered library for the new user
```

The 30-per-60s IP budget is deliberately loose: several sub-accounts share one source IP
on a household LAN, so the per-account 4-attempt lockout is the real brake on guessing a
single PIN. The IP cap exists to stop high-volume automated sweeps across many accounts.

---

## Flow 5: User Switch (sub-account, PIN required)

```text
UserSwitcher: user.pin_required=true OR user.is_locked → setPinTarget(user)

PinModal: user enters PIN → POST /api/v1/auth/switch { user_item_id, pin }
  → same IP rate limit as Flow 4
  → user.is_owner=false, user.pin_required=true
  → _verify_pin → FAIL → attempts++ → lock at 4 → 401
  → _verify_pin → PASS → attempts=0 → issue_session → Set-Cookie (peach_token, peach_csrf) → return user
```

---

## Flow 6: User Switch (sub-account, no PIN)

```text
UserSwitcher: user.pin_required=false AND user.id != activeId AND !user.is_locked
  → direct call POST /api/v1/auth/switch { user_item_id, pin: "" }
    → same IP rate limit as Flow 4
    → user.is_owner=false, pin_required=false
    → skip PIN check → failed_pin_attempts=0 → issue_session → Set-Cookie → return user
  → dispatch SET_ACTIVE_USER
```

---

## Flow 7: Session Refresh (on every app open)

```text
AppProvider: after a successful GET /auth/me, calls POST /api/v1/auth/refresh
  → reads peach_token from cookie, parse_session_cookie → (user_item_id, token)
  → validate_session resolves the current user (401 if missing/expired/mismatched)
  → extend_session(db, user) recomputes session_token_expires_at from
    session_token_ttl only; session_token_hash, and therefore the token itself,
    is never touched
  → _set_auth_cookie re-sent with the *same* already-parsed token and a refreshed
    max_age, but only if session_token_ttl is set (skipped entirely for
    non-expiring sessions, where there is nothing to extend)
  → _set_csrf_cookie → new peach_csrf cookie overwrites the old one
  → return { user: UserItemRead }
  → dispatch SET_ACTIVE_USER(refreshed user)
```

Failure is non-fatal: `catch()` swallows the error and the session from `/auth/me` stays
valid until its own expiry.

**Why refresh does not rotate.** The prior design called `issue_session()` here, minting a
new token and overwriting `session_token_hash` on every refresh. Two legitimate
near-simultaneous refresh calls from the same session (StrictMode double-mount, multiple
browser tabs, network retries) would race: the first call's commit invalidated the token
the second was still presenting, producing a spurious 401 and an auto-sign-out. Token
issuance stays exclusive to `/auth/setup-owner` and `/auth/switch`. Per
[DECISIONS.md](DECISIONS.md) 2026-06-20 this dissolves, rather than violates, the
documented "two-row rollback-safety" tradeoff: refresh never creates a second token, so
there is nothing to roll back.

---

## Flow 8: Logout

```text
Any logout action (no explicit logout button exists in the UI today; reached via session
expiry or a manual call)
  → POST /api/v1/auth/logout
    → read peach_token from cookie
    → parse_session_cookie → (user_item_id, token); validate_session(db, user_item_id, token)
      → only if the token actually validates: clear_session(db, user) nulls
        session_token_hash and session_token_expires_at
      → a present-but-invalid cookie is a no-op, which prevents a guessed or garbage token
        paired with someone else's user_item_id from force-clearing their session without
        proof of possession of their real token
    → response.delete_cookie("peach_token", httponly=True, samesite="lax")
    → response.delete_cookie("peach_csrf", httponly=False, samesite="lax")
    → return { success: true }
  → dispatch LOGOUT → activeUser=null, showUnauthModal=true
```

---

## Flow 9: Create Sub-Account (owner only)

```text
Users page: owner clicks "+ Add Account" → modal opens (button hidden from admin
  sub-accounts; the frontend gates on is_owner, not is_admin)
  → fill name, optional PIN, permissions checkboxes, content rating, session expiry

Owner submits → POST /api/v1/users
  → require_permission("is_owner"). This is owner-only: an is_admin=true sub-account
    gets 403 here even though it can edit/reset-pin/unlock/force-logout existing
    sub-accounts
  → validate PIN (4-6 digits) if provided
  → Argon2id hash PIN
  → insert UserItem row (is_owner=false always)
  → return UserItemRead (pin_hash never returned)
```

---

## Flow 10: Edit Sub-Account Permissions (admin-edits-other, or self-edit via can_manage_users)

```text
Users page: admin edits permissions (no inline edit UI today, PATCH is backend-only)
  → PATCH /api/v1/users/{user_item_id}
    → require_admin_or_self_manage:
        active_user.is_owner OR active_user.is_admin → pass
        else: active_user.id == user_item_id AND active_user.can_manage_users → pass
        else → 403
    → target user.is_owner=true → 403, regardless of which path passed
    → if the caller is owner/admin: apply all fields from UserPatch (name, permissions,
      content rating, pin_required, session_token_ttl)
    → if the caller is self-editing via can_manage_users only: any UserPatch field other
      than name is rejected with 403, so a self-edit cannot touch its own permission
      flags, rating, pin_required, or session_token_ttl
    → db.commit → return updated UserItemRead
```

---

## Flow 11: Reset PIN (admin resets another user's PIN, or self-reset via can_manage_users)

```text
Users page: admin clicks key icon on a user → Reset PIN modal
  → enter new PIN → POST /api/v1/users/{user_item_id}/reset-pin { pin }
    → require_admin_or_self_manage:
        active_user.is_owner OR active_user.is_admin → pass
        else: active_user.id == user_item_id AND active_user.can_manage_users → pass
          (a sub-account resetting its own PIN; the body only ever contains `pin`, so
          the PATCH field-restriction logic is unnecessary here)
        else → 403
    → target user.is_owner → 403 Owner account cannot be modified here
    → target user.is_admin AND active_user is NOT owner → 403 Only the owner can reset
        an admin's PIN (blocks admin-resets-admin and admin-resets-self, regardless of
        lock state)
    → target user.is_locked AND active_user is NOT owner/admin → 403 Account is locked;
        an admin must reset this PIN. Self-reset is unavailable the moment is_locked is
        true, regardless of can_manage_users. Checked in the route handler in addition
        to require_admin_or_self_manage
    → _validate_pin(pin), 4-6 digits, else 422
    → new Argon2id hash
    → user.pin_hash = new_hash, pin_required=true, failed_pin_attempts=0, is_locked=false
    → return UserItemRead
```

Resetting a PIN does not clear `session_token_hash`, so an already-issued session for that
account survives the reset. Use `POST /users/{id}/force-logout` to revoke it.

---

## Flow 12: Unlock Locked Account (admin)

```text
Users page: admin clicks unlock icon on a locked user
  → POST /api/v1/users/{user_item_id}/unlock
    → require_permission("is_admin")
    → target user.is_owner → 403 Owner account cannot be modified here
    → user.is_locked=false, failed_pin_attempts=0
    → return UserItemRead
```

---

## Flow 13: Delete Sub-Account (owner only)

```text
Users page: owner clicks trash icon → browser confirm() dialog (button hidden from admin
  sub-accounts; the frontend gates on is_owner, not is_admin)
  → DELETE /api/v1/users/{user_item_id}
    → require_permission("is_owner"), owner-only. There is no self-delete side door:
      an admin sub-account can no longer delete itself or any other sub-account
      (this replaced require_self_or_admin, which previously allowed both)
    → target user.is_owner → 403. Since only the owner can call this endpoint at all,
      the only way the target is the owner is the owner targeting their own account,
      so this guard is what actually blocks owner self-deletion
    → delete MediaRestriction rows for user_item_id
    → reassign ProfileItem.user_item_id → owner.id (profiles are not deleted)
    → db.delete(user) → commit → 204
```

---

## Flow 14: Owner Lockout Recovery (CLI)

```text
Owner locked out (4+ failed PINs) or PIN forgotten
  → Run: python scripts/setup_admin_user.py
    → reads the DB path via backend.core.settings.get_db_path()
      (fixed at database/data/peach1up.db, not configurable)
    → registers a PRAGMA foreign_keys=ON connect listener on its standalone engine
    → prompt: Owner name, PIN, confirm PIN
    → if an owner exists: overwrite name and pin_hash, re-grant every permission flag,
      reset failed_pin_attempts=0, is_locked=false
    → if no owner: create the owner row with id=1
    → commit
    → no web session is issued; the user must switch to the owner account in the UI on
      the next launch
```

This script does not clear `session_token_hash`, so a session issued before the reset
stays valid until it expires or is explicitly revoked.

⚠ **This script currently fails at runtime.** See the flagged item at the end of this
document.

---

## Flow 15: Permission Check on Any Protected API Endpoint

```text
Request arrives with peach_token cookie
  → get_active_user(request, db):
    → cookie missing → 401
    → parse_session_cookie fails (no separator, or non-numeric user_item_id) → 401
    → validate_session: user missing, session_token_hash is NULL (logged out), token
      expired, or the presented token doesn't match the stored hash → 401
    → return UserItem

require_permission("some_flag")(active_user):
  → active_user.is_owner → pass (owner bypasses all flags)
  → getattr(active_user, "some_flag", False) → False → 403
  → True → pass

require_self_or_admin:
  → active_user.id == path user_item_id → pass
  → active_user.is_admin → pass
  → else → 403
```

`dependencies.py` also exposes two coarser gates used by non-user routers:
`require_owner_or_admin` (owner or admin) and `require_game_or_environment_editor`
(owner, `can_manage_game`, or `can_manage_environment`).

---

## Flow 16: Content Rating / Media Restriction (collection filtering)

```text
GET /api/v1/software (or any endpoint using get_filtered_game_item_bundles)
  → get_active_user → user
  → get_filtered_game_item_bundles(user, db):
    → user.is_owner → return all collections (no filter)
    → exclude collections listed in MediaRestriction for this user_item_id. The same
      table also spans media_item_bundle_id and app_item_bundle_id for the Media and App
      domains, with exactly one of the three FKs set per row
    → block_unrated_media=true → exclude collections WHERE content_rating IS NULL OR ""
    → max_content_rating set → load rating_ordinals from settings, or the defaults in
      dependencies.py (⚠ no write path exists today, see SECURITY.md Known Gaps)
      → compute the allowed set: all ratings with ordinal <= max
      → the filter FAILS CLOSED. A collection passes only if its rating is NULL/empty or
        in the allowed set. An unrecognised rating is DENIED, not passed through, and if
        the user's own ceiling cannot resolve to a known ordinal, no rated content passes
```

Parallel filters exist for the other domains: `get_filtered_app_items`,
`get_filtered_media_item_bundles`, `get_filtered_media_items`, plus the single-item
variants `get_filtered_game_item_bundle`, `get_filtered_app_item`,
`get_filtered_media_item_bundle`, and `get_filtered_media_item`, which return 404 rather
than 403 on a filtered-out item.

MediaRestriction rows are managed by admins via
`GET/PUT /api/v1/softwarecollection/{collection_id}/restrictions` (requires `is_admin`).

---

## Flow 17: Destructive Operation Confirmation Token

```text
Example: delete software collection

Step 1. POST /api/v1/softwarecollection/{collection_id}/confirm-delete
  → require_permission("can_manage_game")
  → confirmation_tokens.issue("software", collection_id) → in-memory store, 60s TTL
  → return { confirmation_token, expires_in_seconds: 60 }

Step 2. DELETE /api/v1/softwarecollection/{collection_id}?confirmation_token=<token>
  → require_permission("can_manage_game")
  → confirmation_tokens.consume(token, "software", collection_id) validates type, id, expiry
  → FAIL → 400 "Invalid or expired confirmation token"
  → PASS → delete collection
```

The same pattern applies to environment delete, drive delete, and snapshot
delete/restore. Admin sandbox reset uses `install_registry`'s own confirm token with the
same TTL model. `TOKEN_TTL` lives in
[`backend/service/utils/confirmation_tokens.py`](../backend/service/utils/confirmation_tokens.py).

---

## Flow 18: First-Run Already Completed (owner_exists but flag not set)

```text
Edge case: the DB has an owner but the first_run_complete flag is missing (e.g. restored DB)

Browser opens /first-run
  → GET /api/v1/settings/first-run-status
    → first_run_complete=false, owner_exists=true
  → FirstRun renders the "Setup Complete" screen, not the owner-creation form
  → User clicks "Continue" → POST /api/v1/settings/complete-first-run
    → require_permission("can_manage_settings") → must be authenticated as owner
    → writes first_run_complete="true", sets the in-memory cache
```

---

## GET /api/v1/users: Intentionally Unauthenticated

`GET /api/v1/users` has no auth dependency; `list_users(db)` takes no active-user check.
It returns only `UserItemRead`, which excludes `pin_hash`, `session_token_hash`, and
`identity_token_secret`, so it never exposes anything that proves identity or grants
access.

Why: this is the data source for the switch-account screen
([`frontend/src/pages/Users`](../frontend/src/pages/Users/index.tsx)) that a signed-out
user lands on. `POST /api/v1/auth/switch` already requires no prior session, since you
present a `user_item_id` plus PIN rather than a cookie, so gating the *list* of users
behind auth created a lockout: a session-expired user was redirected to `/users` to log
back in, but the page's own `GET /api/v1/users` call 401'd, leaving no way to see which
account to switch to.

All other endpoints on this router remain gated:

| Endpoint | Guard |
|----------|-------|
| `GET /api/v1/users/{id}` | `Depends(get_active_user)` |
| `POST /api/v1/users` | `require_permission("is_owner")` (Flow 9) |
| `DELETE /api/v1/users/{id}` | `require_permission("is_owner")` (Flow 13) |
| `PATCH /api/v1/users/{id}` | `require_admin_or_self_manage` (Flow 10) |
| `POST /api/v1/users/{id}/reset-pin` | `require_admin_or_self_manage` (Flow 11) |
| `POST /api/v1/users/{id}/unlock` | `require_permission("is_admin")` (Flow 12) |
| `POST /api/v1/users/{id}/force-logout` | `require_permission("is_admin")` |

All five mutating-by-id endpoints carry an owner-target guard regardless of which path let
the caller in.

---

## Secrets Never Exposed

- `pin_hash`: excluded from `UserItemRead`, never returned by any endpoint.
- `identity_token_secret` and `session_token_hash`: server-only columns, excluded from
  `UserItemRead`.
- Session token value: set as a cookie only, never in a response body, never logged.
- IGDB / TheGamesDB / third-party API keys: `.env` only, never returned by the API. See
  the TheGamesDB query-parameter caveat in [SECURITY.md](SECURITY.md) Known Gaps.

`RequestLoggingMiddleware` logs only method, path, status code, and duration, so no
request or response headers reach the log at all.

---

## Known Gaps (auth-specific)

All gaps identified at audit time have been resolved.

| Gap | Fix |
|-----|-----|
| `GET /api/v1/users` had no auth guard | Added `Depends(get_active_user)` in `users.py`. **Superseded 2026-06-21** (see the row below): the guard was removed again once Users moved to its own route, and the endpoint is now intentionally unauthenticated |
| `GET /api/v1/users` required auth, but it is the data source for the switch-account screen a signed-out user is redirected to, a circular lockout | Removed the auth dependency from `list_users`. `UserItemRead` excludes all secrets, so this exposes nothing sensitive; mutating endpoints on the same router are unaffected. `users.py` |
| Duplicate `GET /auth/me` in `AppShell` | Removed the redundant call; `AppProvider` is the single source. `AppShell.tsx` |
| `complete-first-run` implicit trust | Not a real gap: the owner session from `setup-owner` satisfies `can_manage_settings`. Recorded here for clarity |
| No CSRF protection | `CSRFMiddleware` added (double-submit cookie). `peach_csrf` non-HttpOnly cookie set on every token issue; `X-CSRF-Token` header required on all mutating non-auth requests. `security.py`, `main.py`, `auth.py`, `client.ts` |
| `session-expired` fired on 403, so a locked-account switch logged out the active user | `isSessionError` simplified to `res.status === 401` only. `client.ts` |
| No session refresh or expiry warning | `POST /api/v1/auth/refresh` added, called on every app open in `AppContext`. `auth.py`, `AppContext.tsx` |
| Refresh rotated the session token via `issue_session`, 401-ing a second concurrent refresh call presenting the now-stale token | `refresh_session` now calls `extend_session` (validate-and-extend, never rotates). `identity.py`, `auth.py`. The frontend `AppProvider` mount effect also gained a `useRef` guard as defence in depth. `AppContext.tsx` |
| `AppShell`'s `showUnauthModal` effect redirected to `/settings`, a stale target from before Users moved to `/users`, so anyone signed out while on `/users` was bounced to a page that could not help them sign back in | Redirect target changed to `/users`. `AppShell.tsx` |
| `/auth/switch` had no rate limit, leaving PIN guessing bounded only by the per-account lockout | IP-keyed sliding-window limiter (30 requests / 60s) added via `backend/core/rate_limit.py`. `auth.py` |

*Note: the earlier fixes were implemented against the original `auth_tokens` table and
`token_store.py` model, superseded on 2026-06-20 by the identity/session model in
[`backend/core/identity.py`](../backend/core/identity.py) (see
[DECISIONS.md](DECISIONS.md)). `token_store.py` and the `auth_tokens` table no longer
exist. The gaps and their fixes remain valid; only the underlying token-storage mechanism
changed.*

---

## Open Flag

**`scripts/setup_admin_user.py` raises `ImportError` on every run.** Line 65 does
`from backend.models.user import User`, but
[`backend/models/user.py`](../backend/models/user.py) defines only `UserItem`,
`UserItemBase`, and `UserItemRead`; there is no `User` symbol and no alias. The
owner-lockout recovery path documented in Flow 14, and referenced as the sole owner PIN
recovery mechanism in [SECURITY.md](SECURITY.md), therefore cannot complete. This is a
code defect, recorded here rather than fixed, since this document is the audit surface and
not the fix.
