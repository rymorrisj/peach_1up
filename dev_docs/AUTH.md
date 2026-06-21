# Peach 1UP — Auth System Reference

Complete map of every auth flow, token/cookie lifecycle, permission model, CORS, and
middleware chain. Read alongside `SECURITY.md` (policy rules) and `TECH.md` (stack).

---

## Directory / File Index

| Path | Purpose |
|------|---------|
| `backend/main.py` | Mounts all routers; sets middleware order (CORS → Security → CSRF → FirstRunGuard → router) |
| `backend/api/middleware/security.py` | `SecurityMiddleware` (localhost enforcement, X-Request-ID), `CSRFMiddleware` (double-submit cookie), `FirstRunGuardMiddleware` (redirect to /first-run), CORS config |
| `backend/api/routes/auth.py` | `/api/v1/auth` — setup-owner, switch, logout, me, refresh |
| `backend/api/routes/users.py` | `/api/v1/users` — CRUD users, reset-pin, unlock |
| `backend/api/routes/settings.py` | `/api/v1/settings` — first-run-status, complete-first-run, patch settings |
| `backend/core/dependencies.py` | `get_active_user`, `require_permission`, `require_self_or_admin`, `get_filtered_library` |
| `backend/core/identity.py` | `generate_identity_secret`, `mint_session_token`, `issue_session`, `clear_session`, `validate_session`, `parse_session_cookie` — HMAC-derived session tokens, no separate token table |
| `backend/models/user.py` | `User` DB model + `UserRead` response schema; carries `identity_token_secret`, `session_token_hash`, `session_token_expires_at`, `session_token_ttl` |
| `backend/models/media_restriction.py` | `MediaRestriction` — per-user item block list |
| `backend/core/lifespan.py` | Startup: DB init, first-run flag sync, owner-exists check |
| `scripts/setup_admin_user.py` | CLI emergency owner reset (bypasses web, writes DB directly) |
| `frontend/src/api/client.ts` | `ApiClient` — all requests, `credentials: "include"`, `X-CSRF-Token` header on mutating requests, session-expired event dispatch |
| `frontend/src/context/AppContext.tsx` | Mounts provider; calls `GET /auth/me` on load then `POST /auth/refresh` to rotate token; listens for `session-expired` event |
| `frontend/src/context/_AppContext.ts` | `AppState`, `AppAction`, `appReducer` — `activeUser`, `showUnauthModal` |
| `frontend/src/pages/FirstRun/index.tsx` | Wizard shell; polls first-run-status; calls complete-first-run |
| `frontend/src/pages/FirstRun/Step0Owner.tsx` | Form that calls `POST /auth/setup-owner` and sets `activeUser` |
| `frontend/src/components/UserSwitcher.tsx` | User-switch UI; PIN modal; calls `POST /auth/switch` |
| `frontend/src/components/layout/AppShell.tsx` | Shows signed-out banner on `showUnauthModal`; navigates to /settings when unauthenticated |
| `frontend/src/pages/Settings/UsersTab.tsx` | Admin UI — create user, reset PIN, unlock, delete |

---

## Token & Cookie Model

| Property | Value |
|----------|-------|
| Session cookie name | `peach_token` |
| Session cookie flags | `HttpOnly`, `SameSite=Lax`, `Secure=False` (localhost only) |
| CSRF cookie name | `peach_csrf` |
| CSRF cookie flags | **Not** HttpOnly (JS-readable), `SameSite=Lax`, `Secure=False`; same `max_age` as session token |
| CSRF enforcement | `CSRFMiddleware` — all state-mutating requests must send `X-CSRF-Token` header matching `peach_csrf` value; auth endpoints (`/api/v1/auth/*`) exempt |
| Token storage | Columns on the `User` row — `identity_token_secret`, `session_token_hash`, `session_token_expires_at`, `session_token_ttl`. No separate table |
| Token value | `mint_session_token(identity_token_secret)` → HMAC-SHA256(`identity_token_secret`, `nonce + issued_at`), hex digest. Cookie stores `{user_id}.{session_token}`; only `hash_session_token()` (plain SHA-256) of it is persisted |
| Default expiry | No expiry (`session_token_expires_at = NULL`) unless `User.session_token_ttl` (minutes) is set |
| Multiple sessions | Not allowed — one active session per user by design. `issue_session()` overwrites `session_token_hash` directly, so a new login naturally invalidates any prior session |
| Revocation | `clear_session()` nulls `session_token_hash` and `session_token_expires_at` on the user row — used by `/auth/logout`; no row to delete |
| Session validation | `validate_session(db, user_id, token)` — None if user missing, None if `session_token_hash` is `NULL` (logged out), None if `session_token_expires_at` has passed, then `hmac.compare_digest` of the hash against the presented token |
| Expired/revoked cleanup | None needed — no accumulated rows. Expiry and revocation are point-in-time checks against the single hash column, not a cleanup job |
| Frontend sends cookie | Every request via `credentials: "include"` in `ApiClient.fetch` |
| Frontend sends CSRF | `ApiClient.fetch` reads `peach_csrf` from `document.cookie` and adds `X-CSRF-Token` header on all non-GET/HEAD/OPTIONS requests |

---

## Permission Flags

| Flag | Default for owner | Default for sub-account | What it gates |
|------|:-:|:-:|------|
| `is_owner` | `True` | always `False` | Bypasses all `require_permission` checks; owner-only operations |
| `is_admin` | `True` | `False` | All permission flags; cannot grant owner powers |
| `can_launch_media` | `True` | `True` | Launch any permitted library item |
| `can_edit_library` | `True` | `False` | Add/edit/delete library items and drive |
| `can_edit_platforms` | `True` | `False` | Register/modify OS platforms |
| `can_manage_profiles` | `True` | `False` | Create/modify sub-accounts |
| `can_edit_settings` | `True` | `False` | Modify application settings |

`require_permission(flag)` in `dependencies.py`: owner bypasses unconditionally; others must have the boolean flag set. Returns 403 on failure.

---

## Middleware Chain (LIFO — last-added runs first)

```
Browser request
  → CORSMiddleware          — preflight handling; allow_origins defaults to ["http://localhost:5173"] + optional CORS_ORIGIN env
  → SecurityMiddleware      — reject non-localhost clients when ALLOW_NETWORK_ACCESS=false; inject X-Request-ID
  → CSRFMiddleware          — double-submit cookie check for all state-mutating requests; exempt: safe methods, /api/v1/auth/* endpoints, requests with no session cookie
  → FirstRunGuardMiddleware — redirect non-API, non-asset, non /first-run paths to /first-run when first_run_complete is false
  → Router / Handler
```

CORS origins: `http://localhost:5173` always included; `CORS_ORIGIN` env var adds one override. `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.

`FirstRunGuardMiddleware` reads `_first_run_done_cache` (in-memory bool set at startup from DB and again when `complete-first-run` is called). No DB query per request.

`CSRFMiddleware`: if no `peach_token` cookie is present the check is skipped entirely, so unauthenticated callers get a 401 from the auth dependency rather than a misleading 403.

OPTIONS requests bypass both `SecurityMiddleware` and `FirstRunGuardMiddleware`.

---

## Flow 1 — First Launch (no owner, no DB)

```
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
    → check: no existing owner → pass
    → validate: name non-empty, PIN 4-6 digits, PINs match
    → Argon2id hash PIN → create User(is_owner=true, is_admin=true, all permissions=true,
      identity_token_secret=generate_identity_secret())
    → issue_session(db, owner) → mint HMAC session token, store its hash on the user row
    → Set-Cookie: peach_token=<user_id>.<token>; HttpOnly; SameSite=Lax
    → Set-Cookie: peach_csrf=<random>; SameSite=Lax (JS-readable)
    → return { user: UserRead }
  → Frontend: dispatch SET_ACTIVE_USER
  → Frontend: call POST /api/v1/settings/complete-first-run
    → require_permission("can_edit_settings") → owner → pass
    → write settings row first_run_complete="true"
    → set_first_run_complete() → _first_run_done_cache = true
  → Frontend: window.location.replace("/") → full reload → redirect to /library
```

---

## Flow 2 — Normal App Boot (owner exists, session may exist)

```
App starts
  → lifespan: DB ready, first_run_complete=true → _first_run_done_cache=true
  → FirstRunGuardMiddleware inactive (passthrough)

Browser opens app
  → AppProvider mounts → calls GET /api/v1/auth/me
    → cookie peach_token present?
      → YES → parse_session_cookie splits it into (user_id, token); validate_session
               checks session_token_hash matches and not expired → return User
               → dispatch SET_ACTIVE_USER (also clears showUnauthModal)
               → then calls POST /api/v1/auth/refresh (non-fatal)
                 → issue_session mints a new token and overwrites session_token_hash
                   directly (one session per user — no old row to revoke)
                 → new peach_token + peach_csrf cookies set
                 → dispatch SET_ACTIVE_USER with refreshed user
      → NO  → 401 → dispatch LOGOUT → showUnauthModal=true
```

---

## Flow 3 — Session Expiry / Token Invalid Mid-Session

```
Any API call with a cookie that fails validation (no hash set, expired, or token mismatch)
  → Backend: validate_session returns None → 401 Unauthorized

ApiClient.fetch receives 401
  → isSessionError = true
  → dispatch CustomEvent("session-expired")

AppProvider listener fires
  → dispatch LOGOUT → activeUser=null, showUnauthModal=true

AppShell detects showUnauthModal=true
  → navigate("/settings")
  → renders signed-out banner "You have been signed out. Please sign in to continue."

User clicks another account in UserSwitcher → PIN modal → POST /auth/switch → new token issued
```

---

## Flow 4 — User Switch (owner account)

```
UserSwitcher: user clicks owner card (always requires PIN even if already active)
  → setPinTarget(owner)

PinModal renders → user enters PIN → form submit
  → POST /api/v1/auth/switch { user_id: <owner_id>, pin: "<pin>" }
    → fetch user by id
    → user.is_locked? → 403
    → user.is_owner=true → require non-empty PIN
    → _verify_pin(pin, pin_hash) via argon2.PasswordHasher.verify()
      → FAIL → failed_pin_attempts++ → if >=4: is_locked=true → 401
      → PASS → failed_pin_attempts=0 → issue_session → Set-Cookie (peach_token, peach_csrf) → return user
  → dispatch SET_ACTIVE_USER(owner)
  → queryClient.invalidateQueries(["library"]) — re-fetches filtered library for new user
```

---

## Flow 5 — User Switch (sub-account, PIN required)

```
UserSwitcher: user.pin_required=true OR user.is_locked → setPinTarget(user)

PinModal: user enters PIN → POST /api/v1/auth/switch { user_id, pin }
  → user.is_owner=false
  → user.pin_required=true
  → _verify_pin → FAIL → attempts++ → lock at 4 → 401
  → _verify_pin → PASS → attempts=0 → issue_session → Set-Cookie (peach_token, peach_csrf) → return user
```

---

## Flow 6 — User Switch (sub-account, no PIN)

```
UserSwitcher: user.pin_required=false AND user.id != activeId AND !user.is_locked
  → direct call POST /api/v1/auth/switch { user_id, pin: "" }
    → user.is_owner=false, pin_required=false
    → skip PIN check → failed_pin_attempts=0 → issue_session → Set-Cookie (peach_token, peach_csrf) → return user
  → dispatch SET_ACTIVE_USER
```

---

## Flow 7 — Session Refresh (on every app open)

```
AppProvider: after successful GET /auth/me, calls POST /api/v1/auth/refresh
  → reads peach_token from cookie, parse_session_cookie → (user_id, token)
  → validate_session resolves current user (401 if missing/expired/mismatched)
  → issue_session(db, user) → mints a new HMAC token, overwrites session_token_hash
    directly on the same User row (one session per user — no old row to revoke)
  → _set_auth_cookie → new peach_token cookie overwrites old
  → _set_csrf_cookie → new peach_csrf cookie overwrites old
  → return { user: UserRead }
  → dispatch SET_ACTIVE_USER(refreshed user)

Failure is non-fatal — catch() swallows the error; the original session from /auth/me remains
valid until its own expiry. Note: under one-session-per-user there is no rollback safety — a
failed refresh simply leaves the prior (still-valid) session in place, since no second row ever
existed to roll back to. This is an accepted tradeoff; see DECISIONS.md 2026-06-20.
```

---

## Flow 8 — Logout

```
Any logout action (no explicit logout button exists in UI currently — flow via session expiry or manual)
  → POST /api/v1/auth/logout
    → read peach_token from cookie
    → parse_session_cookie → (user_id, token); validate_session(db, user_id, token)
      → only if the token actually validates: clear_session(db, user) nulls
        session_token_hash and session_token_expires_at
      → a present-but-invalid cookie is a no-op — prevents a guessed/garbage token paired
        with someone else's user_id from force-clearing their session with no proof of
        possession of their real token
    → response.delete_cookie("peach_token", samesite="lax")
    → response.delete_cookie("peach_csrf", httponly=False, samesite="lax")
    → return { success: true }
  → dispatch LOGOUT → activeUser=null, showUnauthModal=true
```

---

## Flow 9 — Create Sub-Account (admin only)

```
UsersTab: admin clicks "+ Add Account" → modal opens
  → fill name, optional PIN, permissions checkboxes, content rating, session expiry

Admin submits → POST /api/v1/users
  → require_permission("is_admin") → owner bypasses; non-owner needs is_admin=true
  → validate PIN (4-6 digits regex) if provided
  → Argon2id hash PIN (argon2.low_level.hash_secret, urandom(16) salt)
  → insert User row (is_owner=false always)
  → return UserRead (pin_hash never returned)
```

---

## Flow 10 — Edit Sub-Account Permissions

```
UsersTab: admin edits permissions (currently no inline edit UI — PATCH is backend-only)
  → PATCH /api/v1/users/{user_id}
    → require_permission("is_admin")
    → target user.is_owner=true → 403 (owner cannot be modified here)
    → apply fields from UserPatch (name, permissions, content rating, pin_required, session_token_ttl)
    → db.commit → return updated UserRead
```

---

## Flow 11 — Reset PIN (admin resets another user's PIN)

```
UsersTab: admin clicks key icon on a user → Reset PIN modal
  → enter new PIN → POST /api/v1/users/{user_id}/reset-pin { pin }
    → require_permission("is_admin")
    → _validate_pin(pin) — 4-6 digit regex
    → _hash_pin → new Argon2id hash with fresh urandom(16) salt
    → user.pin_hash = new_hash, pin_required=true, failed_pin_attempts=0, is_locked=false
    → return UserRead
```

---

## Flow 12 — Unlock Locked Account (admin)

```
UsersTab: admin clicks unlock icon on a locked user
  → POST /api/v1/users/{user_id}/unlock
    → require_permission("is_admin")
    → user.is_locked=false, failed_pin_attempts=0
    → return UserRead
```

---

## Flow 13 — Delete Sub-Account (admin)

```
UsersTab: admin clicks trash icon → browser confirm() dialog
  → DELETE /api/v1/users/{user_id}
    → require_self_or_admin: active_user.id == user_id OR active_user.is_admin
    → target user.is_owner → 403
    → delete MediaRestriction rows for user_id
    → reassign Profile.user_id → owner.id (profiles are not deleted)
    → db.delete(user) → commit
```

---

## Flow 14 — Owner Lockout Recovery (CLI)

```
Owner locked out (4+ failed PINs) or PIN forgotten
  → Run: python scripts/setup_admin_user.py
    → reads DB path from config/settings.yaml (falls back to database/data/peach1up.db)
    → prompt: Owner name, PIN, confirm PIN
    → if owner exists: overwrite name, pin_hash, reset failed_pin_attempts=0, is_locked=false
    → if no owner: create User(id=1, is_owner=true, all permissions=true)
    → commit
    → no web session issued — user must switch to owner account in UI next launch
```

---

## Flow 15 — Permission Check on Any Protected API Endpoint

```
Request arrives with peach_token cookie
  → get_active_user(request, db):
    → cookie missing → 401
    → parse_session_cookie fails (no separator / non-numeric user_id) → 401
    → validate_session: user missing, session_token_hash is NULL (logged out), token expired,
      or presented token doesn't match the stored hash → 401
    → return User

require_permission("some_flag")(active_user):
  → active_user.is_owner → pass (owner bypasses all flags)
  → getattr(active_user, "some_flag", False) → False → 403
  → True → pass

require_self_or_admin:
  → active_user.id == path user_id → pass
  → active_user.is_admin → pass
  → else → 403
```

---

## Flow 16 — Content Rating / Media Restriction (library filtering)

```
GET /api/v1/library (or any library endpoint using get_filtered_library)
  → get_active_user → user
  → get_filtered_library(user, db):
    → user.is_owner → return all items (no filter)
    → exclude items in MediaRestriction WHERE user_id=user.id
    → block_unrated_media=true → exclude items WHERE content_rating IS NULL OR ""
    → max_content_rating set → load rating_ordinals from settings.yaml (or defaults)
      → compute allowed set: all ratings with ordinal ≤ max
      → filter: item passes if rating is NULL/empty, in allowed set, or unknown (foreign ratings pass through)
```

MediaRestriction rows are managed by admin via `GET/POST /api/v1/library/{item_id}/restrictions` (requires `is_admin`).

---

## Flow 17 — Destructive Operation Confirmation Token

```
Example: delete library item

Step 1 — GET /api/v1/library/{item_id}/confirm-token
  → require_permission("can_edit_library")
  → confirmation_tokens.issue("library", item_id) → in-memory store, 60s TTL
  → return { confirmation_token, expires_in_seconds: 60 }

Step 2 — DELETE /api/v1/library/{item_id}?confirmation_token=<token>
  → require_permission("can_edit_library")
  → confirmation_tokens.consume(token, "library", item_id) → validates type+id+expiry
  → FAIL → 400 "Invalid or expired confirmation token"
  → PASS → delete item

Same pattern applies to: platform delete, drive delete, snapshot delete/restore.
Admin sandbox reset uses install_registry's own confirm token (same TTL model).
```

---

## Flow 18 — First-Run Already Completed (owner_exists but flag not set)

```
Edge case: DB has owner but first_run_complete flag missing (e.g. DB restored)

Browser opens /first-run
  → GET /api/v1/settings/first-run-status
    → first_run_complete=false, owner_exists=true
  → FirstRun renders "Setup Complete" screen (not the owner-creation form)
  → User clicks "Continue" → POST /api/v1/settings/complete-first-run
    → require_permission("can_edit_settings") → must be authenticated as owner
    → writes first_run_complete="true", sets in-memory cache
```

---

## GET /api/v1/users — Authenticated

```
GET /api/v1/users requires a valid session (Depends(get_active_user)).
Only UserRead is returned (no pin_hash, no token values).
Any authenticated user can list all users; admin flag is not required.
UserSwitcher.tsx fetches this endpoint — it is only rendered in the Settings page
where a session is already established, so the auth requirement is safe.
```

---

## Secrets Never Exposed

- `pin_hash` — excluded from `UserRead`; never returned by any endpoint
- `token` value — set as cookie only; never in response body, never logged
- `Authorization` headers — stripped by middleware before any log output
- IGDB / third-party API keys — `settings.yaml` only; never returned by API
- Recovery key — shown once at first run (see SECURITY.md); stored as Argon2id hash only

---

## Known Gaps (auth-specific) — All Fixed

All gaps identified at audit time have been resolved.

| Gap | Fix |
|-----|-----|
| `GET /api/v1/users` had no auth guard | Added `Depends(get_active_user)` — `users.py` |
| Duplicate `GET /auth/me` in `AppShell` | Removed redundant call; `AppProvider` is the single source — `AppShell.tsx` |
| `complete-first-run` implicit trust | Not a real gap — owner session from `setup-owner` satisfies `can_edit_settings`. Documented here for clarity. |
| No CSRF protection | `CSRFMiddleware` added (double-submit cookie pattern). `peach_csrf` non-HttpOnly cookie set on every token issue; `X-CSRF-Token` header required on all mutating non-auth requests. Auth endpoints (`/api/v1/auth/*`) exempt. — `security.py`, `main.py`, `auth.py`, `client.ts` |
| `session-expired` fired on 403 (locked-account switch logged out active user) | `isSessionError` simplified to `res.status === 401` only — `client.ts` |
| No session refresh / expiry warning | `POST /api/v1/auth/refresh` endpoint added; called on every app open in `AppContext`. — `auth.py`, `AppContext.tsx` |

*Note: the fixes above were implemented against the original `auth_tokens` table / `token_store.py` model. That model was superseded on 2026-06-20 by the identity/session model in `backend/core/identity.py` (see DECISIONS.md) — `token_store.py` and the `auth_tokens` table no longer exist. The gaps and their fixes remain valid; only the underlying token-storage mechanism changed.*
