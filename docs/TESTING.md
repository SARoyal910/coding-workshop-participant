# Testing

Backend tests live in `tests/backend/`, outside `backend/`. That keeps them
out of the Lambda packages and out of the `bandit -r ./backend` CI scan.
Frontend tests sit next to the code they test (`frontend/src/**/*.test.jsx`).

## How to run

Backend (from the repo root, using the backend virtualenv):

```bash
backend/.venv/bin/pip install -r tests/requirements.txt   # pytest, pytest-cov (once)

# Unit + handler tests (no database needed; any attempt to connect fails the test)
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

CI (`.github/workflows/tests.actions.yml`) runs on every push and pull request:
the backend unit and handler tests with coverage, then eslint, Vitest and the
production build for the frontend. The integration tests skip themselves there
because CI has no database.

## Latest results (2026-09-24)

| Suite | Result |
| --- | --- |
| Backend, unit + handler | 508 passed, 18 skipped (integration tests, opt-in) |
| Backend, with `RUN_INTEGRATION=1` | 526 passed. The `public` schema's row counts are unchanged afterwards |
| Frontend (Vitest) | 65 passed in 13 files |

Backend line coverage (pytest-cov):

| Module | Unit only | With integration |
| --- | --- | --- |
| `incidents/rules.py` | 100% | 100% |
| `_shared/http.py`, `shifts.py`, `errors.py` | 100% | 100% |
| `_shared/auth.py` | 95% | 100% |
| `_shared/validation.py` | 99% | 99% |
| `_shared/engineer_stats.py` | 71% | 100% |
| `auth/service.py` | 100% | 100% |
| `auth/repository.py` | 44% | 84% |
| `dashboard/service.py`, `dashboard/function.py` | 100% | 100% |
| `dashboard/repository.py` | 52% | 100% |
| `incidents/service.py` | 75% | 81% |
| `incidents/repository.py` | 36% | 84% |
| `engineers/service.py`, `engineers/function.py` | 75%, 88% | 100%, 100% |
| `facilities/service.py`, `facilities/repository.py` | 51%, 27% | 81%, 68% |
| **Total (`_shared`, `auth`, `incidents`, `dashboard`, `facilities`, `engineers`)** | **70%** | **91%** |

Frontend coverage is 24% of statements. The tested files are well covered:
`StatusChip`, `WorkflowStepper`, `SiteAlertBanner`, `SimilarIncidentsWarning`,
`LoginPage` and `bulk.js` are at 100% of lines, `FormDialog` 97%, `useApiData` 94%,
`lazyWithReload` 92%, `assign.js` 89%, `constants.js` 79% and `WorkLogPanel` 72%.
The larger pages (dashboard, incident list and detail, facilities, engineers,
people, missed shifts) are covered by the backend handler and integration tests
and by browser checks, not by Vitest.

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
  - `recurring_level`: the threshold boundary (2 is not recurring, 3 is), seat beats floor, and a floor pattern needs more than one seat
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
- **Shifts**: day, swing and night shifts, the night shift across midnight, the time between shifts (the next shift is returned), both edges of a shift and summer time. `is_on_shift` includes the start and excludes the end, and for every hour of the day exactly one shift is on.
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
  - recurring and similar: staff get the related tickets and every open duplicate; employees get the counts and only their own tickets (never other people's); bad or unknown `similar` parameters are 400
  - dashboard: 401 without a token; the admin view has a section for every business question; statuses with no tickets are 0; category totals add up their issue types; `needs_reassignment` and `on_shift_now` (with a fixed clock); shift coverage lists every shift, even an empty one; percentages round to whole numbers and are `null` (not 0%) when nothing is resolved; engineers and employees see only their own counts
  - auth: register with a non-acme email (400), with a `role` field (400), with a duplicate email (409); login with a wrong password or an unknown user gives the same 401 message; `/me` without a token (401); refresh; health (200/503)
- **Integration** (real PostgreSQL, `test` schema):
  - register, login and duplicate register
  - create, then status change, then stale version
  - join twice, resolve, second reopen request (409)
  - the join race: while engineer A's "take" is still uncommitted on a second connection, engineer B's join waits, then B is added as a helper; the database also refuses a second primary directly
  - void (204, then 404 for the reporter)
  - facilities: duplicate building name and floor renumber hit the UNIQUE constraints (409), deleting a seat, floor or building with an incident is 409, the repository's foreign-key guard rolls the delete back, and an empty building is deleted with its floors and seats
  - recurring detection on a fresh seat: 2 reports are not a pattern, the 3rd badges all three, the similar check sees 3 open duplicates, and voiding one drops the pattern again
  - missed shift commitments: an acknowledged shift that ended with the ticket still open counts; one blocked during the shift, one resolved before the shift ended and a shift still running do not
  - dashboards: every dashboard query runs on the seeded rows, and the headline numbers match direct counts (active tickets by status, an employee's own tickets, the unassigned pool, shift coverage against the engineer list)
  - engineers: an admin creates an engineer who can then log in, duplicate email is 409, the list is sorted by workload, availability rules and profile edits
- **Frontend**:
  - `StatusChip` labels and the archived state
  - `WorkflowStepper`: active and completed steps, blocked shown as an error on "In progress", archived shows every step complete
  - `RecurringBadge`: nothing without a level, text label (not color alone)
  - `SimilarIncidentsWarning`: no request until issue type and floor are chosen, duplicate links and the recurring warning, silent when nothing matches
  - `FormDialog`: required fields checked before sending, trimmed values with null for empty optional fields, API field errors shown under the field, other errors shown at the top
  - `LoginPage`: the server's "Invalid email or password" in the alert, email trimming, redirect after login
  - `api.js` error mapping: 401 calls the logout handler only when a session exists, a network failure shows the friendly message, 400/409 keep their details, the default 403 message, a non-JSON error body, 204, and the query string

## Known gaps

- **Bugs the tests found (now fixed).** Both returned 500 instead of a clean error. The tests that exposed them now pass:
  - `{"hours": NaN}` on a work log. Python's `json.loads` accepts `NaN`. Fixed: `get_number` rejects non-finite numbers, and `rules.hours_error` also returns an error for NaN.
  - Non-ASCII digits such as `"²"` in `?page=²` or `/api/incidents/²`. `str.isdigit()` is True for them, but `int()` rejects them. Fixed: `get_int` and `match_route` accept only ASCII `0-9` (`isascii()` + `isdecimal()`).
- **A leak the CI run found (now fixed).** Step 8 made the ticket detail also look up recurring counts, and three handler tests didn't fake that call. On a machine with `POSTGRES_*` set they quietly ran read-only queries against that database; without it they returned 500. The fixture now fakes it, and `conftest.py` makes every non-integration test fail if it tries to open a connection.
- **Coverage.**
  - Backend: 91% with integration tests, 70% without (CI runs the 70% set).
  - Frontend: 19%.
  - The success paths of acknowledge, priority, request decisions and work-log edits are not tested.
  - The incident list, detail, form, register, dashboard, facilities, engineers and approvals pages have no tests (the new pages were checked in the browser, see below).
- **Integration tests are opt-in** (`RUN_INTEGRATION=1`) and need a reachable PostgreSQL. CI runs the unit, handler and frontend tests, but not these.
- **No end-to-end browser suite is committed.** During development each feature was checked end to end with headless-browser (Playwright) runs against a throwaway database schema. These covered login errors, the dashboards, filtering, reporting through the form, the workflow dialogs, reopen and approval, void, the engineer tabs, the facilities, engineers and approvals pages (including role-based navigation and redirects), the recurring badges and report-form warning, the mobile layout and session expiry, with no console errors or 5xx responses. Those scripts are not part of the repo, so this is manual validation rather than an automated suite.
- **No load, performance or security testing** (beyond bandit and `npm audit`).
- The handler tests use a fake repository, so they check the service logic but not the SQL. The SQL is only checked by the integration tests.
