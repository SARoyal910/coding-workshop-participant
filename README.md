# Coding Workshop

The goal of this coding workshop is to enable and assess the hands-on skills
of participants through development of a practical technical solution that
solves a theoretical business problem.

## Getting Started

Navigate to [Coding Workshop - Main Guide](./docs/README.md) to get started.

## Coding Workshop Example

Coding workshop organizer(s) will provide instructions to follow by email. Here
below is a real example of requirements and expectations for participant(s):

### Requirements: Business Problem

Our company ACME Inc. is going through a massive organizational transformation
to become a more data-driven organization. Information about teams structure
and performance is currently scattered across multiple systems, making it
difficult to get a comprehensive view of team dynamics and achievements.

We are struggling to answer simple questions like:

* Who are the members of each team?
* Where are the teams located?
* What are the key achievements of each team on a monthly basis?
* How many teams have team leader not co-located with team members?
* How many teams have team leader as a non-direct staff?
* How many teams have non-direct staff to employees ratio above 20%?
* How many teams are reporting to an organization leader?

### Requirements: Technical Solution

As part of this transformation, we are looking to build a centralized team
management tool that will allow us to track team members, team locations,
monthly team achievements, as well as individual-level and team-level metadata.
Initial focus is to provide a self-service capability without any integrations
with other tools such as Employee Directory, Project Tracking, or Performance
Management.

The technical solution involves developing a stand-alone web application using
modern technologies. The application will have the following features:

* User authentication and authorization
* Role-based access control
* CRUD operations for individuals, teams, achievements and metadata
* Search and filter functionality
* Responsive design for mobile and desktop usage

### Requirements: Technology Stack

The following technologies are required to build the application:

* Frontend: HTML, CSS, React.js with React Responsive and Material UI Components
* Backend: Python
* Database: PostgreSQL

The following technologies are good to know, as they are used to manage and
deploy code:

* Version Control: Git, GitHub
* Infrastructure: Terraform
* Deployment Mode: Shell Scripts
* Deployment Target: AWS Serverless (e.g. S3, CloudFront, Lambda, RDS)

### Expectations: Value-Based Outcomes

By the end of the workshop, participants will have developed a functional
web application that meets the requirements outlined above. The application
will be deployed to a cloud environment and accessible via a web browser.
Participants will also gain hands-on experience with modern web development
technologies and best practices.

## Contributing

See the [CONTRIBUTING](./CONTRIBUTING.md) resource for more details.

## License

This library is licensed under the MIT-0 License.
See the [LICENSE](./LICENSE) resource for more details.

## Roadmap

See the
[open issues](https://github.com/citi/coding-workshop-participant/issues)
for a list of proposed roadmap features (and known issues).

## Security

See the
[Security Issue Notifications](./CONTRIBUTING.md#security-issue-notifications)
resource for more details.

## Authors

The following people have contributed to this workshop:

* Colin Heilman - [@heilmancs](https://github.com/heilmancs)
* Eugene Istrati - [@eistrati](https://github.com/eistrati)
* Isaiah Cornelius Smith - [@corneliusmith](https://github.com/corneliusmith)
* Juan Arevalo - [@jparevalo27](https://github.com/jparevalo27)
* Michael Annucci - [@michael-annucci](https://github.com/michael-annucci)

## Feedback

We'd love to hear your feedback! Please:

* ⭐ Star the repository if you find it helpful
* 🐛 Report issues on GitHub
* 💡 Suggest improvements
* 📝 Share your experience

## Testing

Backend tests live in `tests/backend/`, outside `backend/`. That keeps them
out of the Lambda packages and out of the `bandit -r ./backend` CI scan.
Frontend tests sit next to the code they test (`frontend/src/**/*.test.jsx`).

### How to run

Backend (from the repo root, using the backend virtualenv):

```bash
backend/.venv/bin/pip install -r tests/requirements.txt   # pytest, pytest-cov (once)

# Unit + handler tests (no database needed)
backend/.venv/bin/python -m pytest tests/backend

# With coverage
backend/.venv/bin/python -m pytest tests/backend \
  --cov=backend/_shared --cov=backend/auth --cov=backend/incidents --cov=backend/dashboard

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

### Latest results (2026-09-23)

| Suite | Result |
| --- | --- |
| Backend, unit + handler | 328 passed, 5 skipped (integration tests, opt-in) |
| Backend, with `RUN_INTEGRATION=1` | 333 passed. `public` still has 16 users / 60 incidents afterwards |
| Frontend (Vitest) | 26 passed in 4 files |

Backend line coverage (pytest-cov):

| Module | Unit only | With integration |
| --- | --- | --- |
| `incidents/rules.py` | 100% | 100% |
| `_shared/http.py`, `auth.py`, `shifts.py`, `errors.py` | 100% | 100% |
| `_shared/validation.py` | 99% | 99% |
| `auth/service.py`, `auth/function.py` | 100% | 100% |
| `incidents/service.py` | 58% | 64% |
| `incidents/repository.py` | 39% | 55% |
| `dashboard/*` | 0% | 0% |
| **Total (`_shared`, `auth`, `incidents`, `dashboard`)** | **62%** | **79%** |

Frontend coverage is 17% of statements. The tested files are well covered:
`StatusChip`, `WorkflowStepper` and `LoginPage` are at 100% of lines and
`services/api.js` is at 62%. Every other page and component is at 0%.

### What is covered

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
  - integers (booleans rejected), numbers, dates and choices
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
  - auth: register with a non-acme email (400), with a `role` field (400), with a duplicate email (409); login with a wrong password or an unknown user gives the same 401 message; `/me` without a token (401); refresh; health (200/503)
- **Integration** (real PostgreSQL, `test` schema):
  - register, login and duplicate register
  - create, then status change, then stale version
  - join twice, resolve, second reopen request (409)
  - void (204, then 404 for the reporter)
- **Frontend**:
  - `StatusChip` labels and the archived state
  - `WorkflowStepper`: active and completed steps, blocked shown as an error on "In progress", archived shows every step complete
  - `LoginPage`: the server's "Invalid email or password" in the alert, email trimming, redirect after login
  - `api.js` error mapping: 401 calls the logout handler only when a session exists, a network failure shows the friendly message, 400/409 keep their details, the default 403 message, a non-JSON error body, 204, and the query string

### Known gaps

- **Bugs the tests found (now fixed).** Both returned 500 instead of a clean error. The tests that exposed them now pass:
  - `{"hours": NaN}` on a work log. Python's `json.loads` accepts `NaN`. Fixed: `get_number` rejects non-finite numbers, and `rules.hours_error` also returns an error for NaN.
  - Non-ASCII digits such as `"²"` in `?page=²` or `/api/incidents/²`. `str.isdigit()` is True for them, but `int()` rejects them. Fixed: `get_int` and `match_route` accept only ASCII `0-9` (`isascii()` + `isdecimal()`).
- **Coverage is below the 80% target.**
  - Backend: 79% with integration tests, 62% without.
  - Frontend: 17%.
  - The dashboard service has no tests at all (0%).
  - The success paths of acknowledge, priority, request decisions and work-log edits are not tested.
  - The incident list, detail, form, register and dashboard pages have no tests.
  - Recurring-issue detection and missed-shift metrics (DESIGN.md section 10) are not tested yet.
- **Integration tests are opt-in** (`RUN_INTEGRATION=1`) and need a reachable PostgreSQL. CI doesn't run any tests yet: the workflows only run bandit, npm audit and terraform checks.
- **No end-to-end browser suite is committed.** During development each feature was checked end to end with headless-browser (Playwright) runs against a throwaway database schema. These covered login errors, the dashboards, filtering, reporting through the form, the workflow dialogs, reopen and approval, void, the engineer tabs, the mobile layout and session expiry, with no console errors or 5xx responses. Those scripts are not part of the repo, so this is manual validation rather than an automated suite.
- **No load, performance or security testing** (beyond bandit and `npm audit`).
- The handler tests use a fake repository, so they check the service logic but not the SQL. The SQL is only checked by the integration tests.
