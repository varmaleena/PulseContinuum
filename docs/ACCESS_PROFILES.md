# Two profiles, one episode

The default **Care team** profile presents clinical overview, patient workbench and care requests/audit. **Admin & engineering** presents orchestration and AWS telemetry. The same synthetic episode state is shared; switching perspectives does not reset the workflow.

## Local demonstration

With no frontend credentials configured, the explicitly labeled **Demo profiles** selector lets the presenter show both experiences. The care view is the default. This is an exploration mode for synthetic records on a loopback server, not authenticated hospital access.

Care updates poll clinical records every five seconds; it never opens the raw telemetry event stream. Admin receives the authenticated SSE stream.

## Secured deployment

Set these **server-only** variables in the frontend environment:

```dotenv
REQUIRE_JUDGE_AUTH=true
JUDGE_USERNAME=choose-an-admin-username
JUDGE_PASSWORD=use-a-unique-strong-secret
CARE_USERNAME=choose-a-care-username
CARE_PASSWORD=use-a-different-strong-secret
BACKEND_URL=http://private-backend:8000
BACKEND_API_TOKEN=match-the-private-backend-api-token
```

The example strings are placeholders. Provide actual secrets through your hosting secret mechanism, not source control. HTTPS is required for public access. Keep FastAPI private and require its bearer token. Never expose the token through a `NEXT_PUBLIC_*` variable.

Admin/judge credentials may select either profile. Care credentials receive only care access, even if someone forges an admin view cookie or supplies role headers. Missing required admin access configuration fails closed with 503; invalid credentials return 401. A role cookie selects an allowed view and is not proof of identity.

Middleware overwrites internal profile/access headers, redirects care requests away from admin pages, and rejects disallowed API routes with 403. The server proxy also enforces a care endpoint allowlist and strips raw traces, account/request/message identifiers and canonical audit internals from care JSON. Raw `/api/telemetry`, `/api/events` and webhook routes are unavailable in the care profile. Switching uses a same-origin POST and an HttpOnly, SameSite cookie, with Secure enabled over HTTPS. Responses are private and not cached.

## Boundaries

This is a coarse two-profile prototype, not a complete hospital authorization system. It does not implement individual clinician identities, hospital SSO, tenants, patient assignment, consent workflows, access audit retention or emergency access. Admin can inspect synthetic clinical context as part of troubleshooting; there is no separate de-identified engineering tenant. The hosted sign-in form issues an HMAC-authenticated, HttpOnly session cookie with an eight-hour lifetime. Signing keys are derived with domain separation from the private administrator secret. Logout clears the cookie; rotating that secret invalidates existing sessions. Individual session revocation and institutional SSO are not implemented. HTTP Basic credentials remain supported for verification clients. A real deployment requires institutional identity and authorization design.

Direct FastAPI access uses a service bearer token rather than these frontend profiles, which is why the backend must remain private. Do not share that token with users.

## Verification

Run `python tools/verify_judge_access.py` after building the frontend and starting the backend. It verifies anonymous rejection, care routes, blocked admin pages/APIs, forged-header/cookie resistance, clinical JSON redaction, cross-origin switching rejection, authorized admin switching and fail-closed missing configuration.

## Public judge demonstration — explicitly enabled

The deployed hackathon site uses `PUBLIC_DEMO=true` at the user's request. It opens the six synthetic cases and both view profiles without account credentials; `/login` redirects to the overview. This is a public demo selector, not an authentication boundary. The backend still requires its private service token, S3 remains private, outbound messages remain disabled, and the live model allowance remains enforced. Set `PUBLIC_DEMO=false` to restore the authenticated behavior documented above. Do not use public demo mode for real clinical data.
