# Auth Audit

---

Auth, Session, and ACL Audit — Peach 1UP

---

1. SESSION MODEL

Storage mechanism. Pure itsdangerous-backed signed cookies via Starlette SessionMiddleware. The payload is base64-encoded JSON — readable but tamper-proof. https_only=False, so
no Secure flag. max_age is unset, making these session cookies (browser-close expiry). The signing secret is generated as a 64-char hex token on first run, persisted to .env via
get_or_generate_session_secret(), and is never returned in API responses.

Session reads/writes outside auth.py / dependencies.py. None. request.session is accessed in exactly two files: auth.py (lines 71, 88, 101, 107, 125) and dependencies.py (line
54). No other route file touches it.

Module-level singleton user state. None. No global or process-level variable tracks the active user. \_first_run_done_cache in security.py is the only module-level state, and it
controls the first-run guard, not identity.

Does get_active_user write to session on unauthenticated requests? No. get_active_user is read-only: it calls request.session.get("active_user_id") and falls back silently to
owner. It never writes.

Concurrent independent sessions from different clients. Technically per-client cookie jar, but in practice no for the desktop use case. All browser windows on the same machine
share the same localhost:PORT cookie. If a parent and child are both using the app at the same time on the same PC — different browser tabs, same WebView — they share one
active_user_id. Switching in one tab switches for all. There is no per-window session isolation. The \_sessionToken / setSessionToken dead code in client.ts (lines 15–18)
suggests token-based per-window isolation was considered but not implemented.

---

2. IDENTITY AND PIN FLOW

Full call chain from PIN entry to resolved active_user_id:

1. UserSwitcher — user clicks a card → handleCardClick (line 152)
2. If pin_required: setPinTarget(user) → PinModal renders and calls showModal()
3. PinModal.handleSubmit → POST /api/v1/auth/switch { user_id, pin }
4. switch_user (auth.py:77):


    - Lookup User by body.user_id
    - is_locked → 403
    - pin_required = False → clear failed_pin_attempts, write request.session["active_user_id"] = user.id
    - pin_required = True → _verify_pin(body.pin, user.pin_hash) via argon2 ph.verify()
        - Failure: increment failed_pin_attempts; lock if ≥ 4; 401
      - Success: reset failed_pin_attempts; write request.session["active_user_id"] = user.id

5. Frontend calls GET /api/v1/auth/me → reads session → returns resolved user
6. dispatch({ type: 'SET_ACTIVE_USER', payload: me })

Paths where owner access is granted without PIN verification:

┌─────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────┐
│ Path │ Mechanism │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /auth/me with no session │ active_user_id is None → implicit owner fallback (auth.py:125–127) │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /auth/me with stale/deleted user in session │ db.get(User, user_id) returns None → owner fallback │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤
│ POST /auth/setup-owner success │ Directly writes request.session["active_user_id"] = owner.id — no PIN step (auth.py:71) │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤
│ POST /auth/logout │ Clears session; next request resolves to owner without PIN │
├─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────┤
│ AppShell mount │ Calls /auth/me with no session → owner returned; no PIN prompt shown │
└─────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────┘

The implicit owner-on-no-session behavior is not a bug, but it means the owner account is the default identity anytime a session is absent — including immediately after the app
starts. There is no "lock screen" equivalent.

Session expiry. SessionMiddleware has no max_age. Session lifetime = until the browser/WebView closes. No per-account expiry duration is supported anywhere in the codebase.

App open with no session cookie. Backend: GET /auth/me returns the owner object (200). Frontend: AppShell.tsx:13–17 dispatches SET_ACTIVE_USER with owner. UI renders with full
owner permissions immediately.

---

3. ACL ENFORCEMENT

Endpoint inventory — every permission-gated endpoint:

┌────────────────────────────────────────────┬─────────────────────┬───────────────────────────┬──────────────────────────────────────┐
│ Endpoint │ Flag checked │ Check location │ Bypassable via session manipulation? │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ GET /api/v1/users │ is_admin │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/users │ is_admin │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ PATCH /api/v1/users/{id} │ is_admin │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ DELETE /api/v1/users/{id} │ is_admin (inline) │ Route body (users.py:132) │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/users/{id}/reset-pin │ is_admin │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/users/{id}/unlock │ is_admin │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/library │ can_edit_library │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ PATCH /api/v1/library/{id} │ can_edit_library │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ DELETE /api/v1/library/{id} │ can_edit_library │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST, PATCH, DELETE /api/v1/platforms/_ │ can_edit_platforms │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/library/{id}/launch │ can_launch_media │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/environments/{id}/launch │ can_launch_media │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/launches/{id}/stop │ can_launch_media │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ PATCH /api/v1/settings │ can_edit_settings │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/settings/emulator-path │ can_edit_settings │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/settings/library-path │ can_edit_settings │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/settings/complete-first-run │ can_edit_settings │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ GET reset-token, PATCH xemu-assets, etc. │ is_admin │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST/PATCH/DELETE /api/v1/profiles/_ │ can_manage_profiles │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST/PATCH/DELETE /api/v1/tags/_ │ can_edit_library │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST/DELETE /api/v1/drives/_ │ can_edit_library │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/media/{id}/upload │ can_edit_library │ require_permission dep │ No │
├────────────────────────────────────────────┼─────────────────────┼───────────────────────────┼──────────────────────────────────────┤
│ GET health/platforms/\*, GET health/library │ can_edit_platforms │ require_permission dep │ No │
└────────────────────────────────────────────┴─────────────────────┴───────────────────────────┴──────────────────────────────────────┘

Endpoints with no auth check — unprotected or gated only by existence of any session:

┌────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Endpoint │ Issue │
├────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /api/v1/library/{id}/launches (launches.py:69) │ No auth. Any caller sees launch history for any item. │
├────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /api/v1/launches (launches.py:79) │ No auth. Full launch history exposed globally. │
├────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /api/v1/launches/{id} (launches.py:83) │ No auth. Individual launch record exposed. │
├────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /api/v1/filesystem/\* (filesystem.py:55, 75) │ Depends(get_active_user) only — any logged-in user can browse the filesystem. No permission flag. │
├────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /api/v1/library │ Depends(get_active_user) + content filter. Any user can read their allowed library — intentional by design. │
├────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ GET /api/v1/tags (tags.py:25) │ Depends(get_active_user) only — any user can list all tags. │
└────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

The three launch history endpoints are the most significant: in a parental control scenario, a restricted child account with no special permissions can read the full launch
history for every item and every session.

ACL separation. Clean. require_permission is a consistently applied FastAPI dependency. Identity resolution (get_active_user) and ACL enforcement are clearly split. The one
place ACL logic leaks into a route body is DELETE /api/v1/users/{id} at users.py:132, which checks active_user.id != user_id and not active_user.is_admin inline instead of using
require_permission.

CSRF. SECURITY.md line 135 explicitly requires CSRF protection on all state-changing endpoints. No CSRF mechanism exists in the current codebase — no token, no middleware, no
Origin/Referer check beyond the SecurityMiddleware localhost binding. When ALLOW_NETWORK_ACCESS=False the localhost check is the de facto CSRF mitigation. When
ALLOW_NETWORK_ACCESS=True, all POST/PATCH/DELETE endpoints become CSRF-vulnerable to any page open in the same browser session. This directly contradicts SECURITY.md.

---

4. ABSTRACTION READINESS

Files outside auth.py/dependencies.py that directly read request.session: Zero. Session access is perfectly contained.

Files outside auth.py/dependencies.py that read user model fields for auth purposes:

- users.py:132 — inline is_admin check in delete_user (one ACL decision outside require_permission)
- library.py:42–44 — passes active_user to get_filtered_library; that function reads is_owner, block_unrated_media, max_content_rating (content filter, not strictly ACL)
- AppShell.tsx:14–15 — calls /auth/me on mount to seed activeUser state
- UsersTab.tsx:95, ItemDetail.tsx:25 — read activeUser.is_admin / is_owner for frontend-only UI gates (no backend enforcement; acceptable)

Clear seam for alternative auth mechanism. Yes. get_active_user is the single identity resolution point in the entire backend. Replacing it — to read from an Authorization:
Bearer <token> header instead of request.session — would leave all require_permission dependencies, all ACL logic, and all business logic completely untouched. The
setSessionToken export in client.ts confirms this was partially considered. The seam is clean.

Estimate for backend/auth/ package boundary:

- Extract get_active_user, require_permission, get_filtered_library from backend/core/dependencies.py → backend/auth/deps.py
- Move backend/api/routes/auth.py → backend/auth/routes.py
- Update backend/main.py router import (1 line)
- Update 12 route files that import from backend.core.dependencies

Approximately 14 files, ~50 import lines changed, zero behavioral changes. The hard part is not the refactor — it's deciding the boundary (does get_filtered_library belong in
auth or library?). Estimate 1–2 hours purely mechanical work.

---

5. KNOWN BUG — Session switches to sub-account on user creation

Three files are currently modified uncommitted (backend/api/routes/auth.py, frontend/src/components/UserSwitcher.tsx, frontend/src/pages/Settings/UsersTab.tsx). The current code
I can read does not reproduce the bug — the fix is either in progress or already applied but not committed. The analysis below reconstructs the pre-fix path from evidence.

Trace of most likely pre-fix call sequence:

1. Admin opens "Add Account" modal in UsersTab and submits
2. handleAddUser called POST /api/v1/users (correct)
3. A previous version of handleAddUser (or a version of UserSwitcher with a useEffect watching the ['users'] query) also called POST /api/v1/auth/switch for the newly created
   user — either to "preview" the account or as an accidental side effect of auto-selecting the first new item in the refreshed list
4. switch_user wrote request.session["active_user_id"] = new_user.id
5. Frontend state updated to reflect sub-account

Is the trigger frontend or backend? Most likely frontend-triggered. The current create_user backend route has never written to request.session (no session access in users.py at
all). The modifications to UserSwitcher.tsx and UsersTab.tsx point to the frontend as the origin.

Does POST /auth/switch appear in network logs during reproduction? Based on the current code: No, it is not called anywhere in the creation flow. If it appeared in historical
reproduction logs, the trigger was a previous UserSwitcher useEffect or a handleAddUser path that no longer exists. The current code is clean on this front — handleAddUser only
calls POST /api/v1/users then invalidateQueries(['users']) with no subsequent switch or /auth/me call.

---

6. ALPHA SCOPE RECOMMENDATION

Fixing concurrent sessions (per-client cookie isolation) — small or structural?

Structural. The root limitation is architectural: Starlette SessionMiddleware issues one shared cookie per origin. All browser contexts on the same machine share it. True
per-window session isolation requires abandoning cookies for identity and issuing per-client tokens (likely the intent behind the dead \_sessionToken / setSessionToken code in
client.ts). The change chain is:

- get_active_user: read from Authorization: Bearer header instead of session cookie
- POST /auth/switch: return a token in the response body, not just write to session
- POST /auth/logout: invalidate token
- API client (client.ts): store token in memory, attach as header
- AppContext: no change needed if client handles it
- Any component calling auth endpoints: no change if abstracted in apiFetch

Estimate: 4–8 hours of careful work. Not risky, but not a one-liner. Defer post-alpha — for a household with one screen, the shared session is functionally correct.

Clean auth package boundary — worth doing now or after alpha?

After alpha. The current code is already well-structured at the seam: session is contained in 2 files, ACL is consistent via require_permission, and the identity resolution
point is clearly defined. Creating backend/auth/ is a mechanical rename with no user-visible benefit and no unblocking value for alpha. The boundary is ready to draw when
needed; there is no urgency.

---

Security Flags (explicit)

CSRF gap vs. SECURITY.md. SECURITY.md line 135 mandates CSRF protection on all state-changing endpoints. Nothing implements it. When ALLOW_NETWORK_ACCESS=False the localhost
binding is the de facto mitigation. When ALLOW_NETWORK_ACCESS=True, this is a real attack surface. Resolution path: either enforce Origin header check in SecurityMiddleware for
non-local requests or implement a CSRF token mechanism.

Launch history fully open. GET /api/v1/launches, /library/{id}/launches, /launches/{id} have zero auth. Any user — or any process on the machine — can read the complete launch
history. In a parental control scenario this leaks what content was played and when.

\_FIRST_RUN_EXEMPT_PATHS is dead code. Defined at security.py:61 but never referenced in FirstRunGuardMiddleware.dispatch. The guard uses path.startswith("/api/") to let all API
calls through unconditionally. The list creates a false impression of whitelist-style exemption control.

Debug logging not stripped. dependencies.py contains multiple \_log.debug("[DEBUG]...") calls with inline # DEBUG — remove before shipping comments. Benign at DEBUG level but
must be removed before shipping.

Stale try/except in /auth/me. auth.py:117–119 wraps get_settings() in a try/except that does nothing — the import result is discarded and the exception swallowed silently. This
is leftover scaffolding.

\_sessionToken dead code in client.ts. setSessionToken is exported but never called. Leaves a confusing bearer-token auth stub that could mislead future developers or
accidentally be activated.

Redundant Depends(get*active_user) on launch routes. launch_item and launch_environment declare both active_user: User = Depends(get_active_user) and *: User =
require_permission("can_launch_media"). FastAPI deduplicates the dep call correctly, but active_user is not passed to svc.launch_item(), so the explicit dep is resolved and
discarded. Not a bug — just noise.
