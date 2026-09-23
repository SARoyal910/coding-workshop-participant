# Testing

Backend tests live in `tests/backend/`, outside `backend/`. That keeps them
out of the Lambda packages and out of the `bandit -r ./backend` CI scan.
Frontend tests sit next to the code they test (`frontend/src/**/*.test.jsx`).

## How to run

Backend (from the repo root, using the backend virtualenv):

```bash
backend/.venv/bin/pip install -r tests/requirements.txt   # pytest, pytest-cov (once)

# Unit + handler tests (no database needed)
backend/.venv/bin/python -m pytest tests/backend

# With coverage
backend/.venv/bin/python -m pytest tests/backend \
  --cov=backend/_shared --cov=backend/auth --cov=backend/incidents --cov=backend/dashboard \
  --cov=backend/facilities --cov=backend/engineers

# Also run the integration tests (needs the PostgreSQL settings in backend/.env)
RUN_INTEGRATION=1 backend/.venv/bin/python -m pytest tests/backend
```

The integration tests never touch the demo data:

- They drop and re-create a separate `test` schema at the start and drop it again at the end.
- They set `POSTGRES_SCHEMA=test`, so `_shared/db.py` runs `SET search_path TO test` and the app creates and seeds its tables there.
- They use their own seed password and JWT secret.
- They check that the `public` schema's row counts are unchanged afterwards.

Frontend (from `frontend/`):

```bash
npm install
npm test                 # vitest run
npm run test:coverage    # vitest run --coverage
```

## Latest results (2026-09-23)

| Suite | Result |
| --- | --- |
| Backend, unit + handler | 361 passed, 7 skipped (integration tests, opt-in) |
| Backend, with `RUN_INTEGRATION=1` | 368 passed. `public` still has 16 users / 60 incidents afterwards |
| Frontend (Vitest) | 30 passed in 5 files |

Backend line coverage (pytest-cov):

| Module | Unit only | With integration |
| --- | --- | --- |
| `incidents/rules.py` | 100% | 100% |
| `_shared/http.py`, `auth.py`, `shifts.py`, `errors.py` | 100% | 100% |
| `_shared/validation.py` | 99% | 99% |
| `auth/service.py`, `auth/function.py` | 100% | 100% |
| `incidents/service.py` | 58% | 64% |
| `incidents/repository.py` | 39% | 55% |
| `engineers/service.py`, `engineers/function.py` | 74%, 88% | 100%, 100% |
| `facilities/service.py`, `facilities/repository.py` | 51%, 27% | 81%, 68% |
| `dashboard/*` | 0% | 0% |
| **Total (`_shared`, `auth`, `incidents`, `dashboard`, `facilities`, `engineers`)** | **61%** | **80%** |

Frontend coverage is 17% of statements. The tested files are well covered:
`StatusChip`, `WorkflowStepper` and `LoginPage` are at 100% of lines,
`FormDialog` is at 97% and `services/api.js` is at 62%. Every other page and component is at 0%.

## What is covered

- **Workflow rules** (`incidents/rules.py`):
  - every allowed transition, with who may make it and what it requires
  - a set of forbidden transitions
  - `is_permitted` for admin, assigned engineer, pool engineer, reporter and other employee
  - `allowed_transitions` and edit rights
  - visibility (`can_view`): engineers see every active ticket, but archived ones only if they were on them
  - who may add notes (`can_add_note`)
  - join, acknowledge, priority, reopen, decide, void and work-log permissions
  - `hours_error` (0.25 steps, 0.25 to 12)
- **Validation** (`_shared/validation.py`):
  - `@acme.inc` emails, including uppercase and look-alike domains such as `a@acme.inc.evil.com` and `a@notacme.inc`
  - trimming and length limits
  - unknown fields
  - integers (booleans rejected), numbers, booleans (strings and 0/1 rejected), dates and choices
  - pagination limits
  - the password rules, including bcrypt's 72-byte limit
- **HTTP helpers** (`_shared/http.py`):
  - `parse_path` with and without the `/api/<svc>` prefix, and a look-alike prefix such as `/api/authx`
  - route matching (numeric placeholders only)
  - JSON and base64 bodies
  - the error mapping, including a generic 500 that never leaks the exception
  - the one-line request log, which never contains the body or the token
- **Tokens** (`_shared/auth.py`): expired, forged and `alg: none` tokens, the role check (403), the 8h lifetime and a missing secret.
- **Shifts**: day, swing and night shifts, the night shift across midnight, the time between shifts (the next shift is returned), both edges of a shift and summer time.
- **Handlers, with the repository faked**. These tests go through `function.handler`, so routing, token checks and error mapping run too:
  - 401: no token, bad token
  - 404: unknown route, missing ticket, another employee's ticket (404, not 403), an archived ticket the engineer was not on, a voided ticket for non-admins
  - 403: reporter changing status, an engineer who isn't on the ticket changing its status, acknowledging it, adding a note or logging work; engineer editing the title; void by a non-admin
  - 400: block without a reason, resolve without a note, unknown field, bad JSON, create-form errors, page size over the limit
  - 409: invalid transition, stale version (optimistic lock), archived or voided ticket, second pending reopen request
  - joining twice gives 200 with no duplicate engineer; void gives 204
  - facilities (admin only): 401/403 for other roles; 400 for blank or unknown fields and out-of-range floor numbers; 409 for a duplicate name and for deleting a place with incidents, including the race where an incident arrives between the check and the delete; 404 for missing buildings
  - engineers: 403 for employees and for non-admins creating accounts; `role` rejected as an unknown field; 400 for a bad email, shift, phone or a non-boolean `is_available`; 409 for a taken email (no profile written); 403 when an engineer changes someone else's availability; `needs_reassignment` when going unavailable with active tickets
  - approvals queue: admin only, `?type=` filter, unknown type is 400
  - auth: register with a non-acme email (400), with a `role` field (400), with a duplicate email (409); login with a wrong password or an unknown user gives the same 401 message; `/me` without a token (401); refresh; health (200/503)
- **Integration** (real PostgreSQL, `test` schema):
  - register, login and duplicate register
  - create, then status change, then stale version
  - join twice, resolve, second reopen request (409)
  - void (204, then 404 for the reporter)
  - facilities: duplicate building name and floor renumber hit the UNIQUE constraints (409), deleting a seat, floor or building with an incident is 409, the repository's foreign-key guard rolls the delete back, and an empty building is deleted with its floors and seats
  - engineers: an admin creates an engineer who can then log in, duplicate email is 409, the list is sorted by workload, availability rules and profile edits
- **Frontend**:
  - `StatusChip` labels and the archived state
  - `WorkflowStepper`: active and completed steps, blocked shown as an error on "In progress", archived shows every step complete
  - `FormDialog`: required fields checked before sending, trimmed values with null for empty optional fields, API field errors shown under the field, other errors shown at the top
  - `LoginPage`: the server's "Invalid email or password" in the alert, email trimming, redirect after login
  - `api.js` error mapping: 401 calls the logout handler only when a session exists, a network failure shows the friendly message, 400/409 keep their details, the default 403 message, a non-JSON error body, 204, and the query string

## Known gaps

- **Bugs the tests found (now fixed).** Both returned 500 instead of a clean error. The tests that exposed them now pass:
  - `{"hours": NaN}` on a work log. Python's `json.loads` accepts `NaN`. Fixed: `get_number` rejects non-finite numbers, and `rules.hours_error` also returns an error for NaN.
  - Non-ASCII digits such as `"²"` in `?page=²` or `/api/incidents/²`. `str.isdigit()` is True for them, but `int()` rejects them. Fixed: `get_int` and `match_route` accept only ASCII `0-9` (`isascii()` + `isdecimal()`).
- **Coverage is below the 80% target.**
  - Backend: 80% with integration tests, 61% without.
  - Frontend: 17%.
  - The dashboard service has no tests at all (0%).
  - The success paths of acknowledge, priority, request decisions and work-log edits are not tested.
  - The incident list, detail, form, register, dashboard, facilities, engineers and approvals pages have no tests (the new pages were checked in the browser, see below).
  - Recurring-issue detection and missed-shift metrics (DESIGN.md section 10) are not tested yet.
- **Integration tests are opt-in** (`RUN_INTEGRATION=1`) and need a reachable PostgreSQL. CI doesn't run any tests yet: the workflows only run bandit, npm audit and terraform checks.
- **No end-to-end browser suite is committed.** During development each feature was checked end to end with headless-browser (Playwright) runs against a throwaway database schema. These covered login errors, the dashboards, filtering, reporting through the form, the workflow dialogs, reopen and approval, void, the engineer tabs, the facilities, engineers and approvals pages (including role-based navigation and redirects), the mobile layout and session expiry, with no console errors or 5xx responses. Those scripts are not part of the repo, so this is manual validation rather than an automated suite.
- **No load, performance or security testing** (beyond bandit and `npm audit`).
- The handler tests use a fake repository, so they check the service logic but not the SQL. The SQL is only checked by the integration tests.
