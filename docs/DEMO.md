# ACME Incidents – Demo Guide

How to log in to the deployed app and walk through it as each role in about 8 minutes.

## Live app

**https://d1k80r5ylurww7.cloudfront.net**

Deployed to AWS (CloudFront + S3 for the frontend, five Python Lambda services,
Aurora PostgreSQL Serverless v2) with the scripts in `bin/`. See
[DESIGN.md](DESIGN.md) section 14 for how it is deployed.

## Demo accounts

Every seeded account uses the **same password**. It is not stored in this repo,
because the repo is public and the admin account can change live data.

- **Reviewers:** the password is shared with you separately (with the submission).
- **Project owner:** print it with
  `cd infra && source ../ENVIRONMENT.config && AWS_REGION=us-east-2 terraform output -raw seed_password`.

| Role | Email | Good for showing |
| --- | --- | --- |
| Admin | `admin@acme.inc` (Alex Morgan) | Dashboard, approvals, reassign, people and roles, missed shifts |
| Engineer | `priya.nair@acme.inc` | The busiest engineer (IT, day shift) |
| Engineer | `lena.ortiz@acme.inc` | Four missed shift commitments (AV, swing shift) |
| Engineer | `tom.becker@acme.inc` | Facilities, day shift |
| Engineer | `sam.okafor@acme.inc` | Security, night shift |
| Engineer | `jordan.lee@acme.inc` | IT, swing shift |
| Employee | `dana.whitfield@acme.inc` | Recurring Wi-Fi tickets at seat 12-A-034 |
| Employee | `luis.romero@acme.inc`, `mei.chen@acme.inc`, `grace.kim@acme.inc`, `ben.carter@acme.inc`, `aisha.patel@acme.inc` and others | Other reporters |

New employees can also register themselves with any `@acme.inc` email.

## Before you start

1. **Wake the database.** Open the site and log in once, a few minutes early.
   The database pauses when nobody uses it, so the first page can take about 15 seconds.
2. **Use a separate browser for each role.** A login is stored per browser, so
   two windows of the same browser share one login. Use, for example, Chrome
   for the admin, Edge for the engineer and a private window for the employee.
3. **If a page shows "Something went wrong"** in a browser that was open before a
   deploy, press **Ctrl+Shift+R** once.
4. Addresses look like `…/#/incidents/58`. The `#` is intentional (see
   [DESIGN.md](DESIGN.md) section 8).

## Walkthrough

### 1. Employee (Dana): report a problem – about 1½ minutes
1. **Dashboard:** her total reported, then one tile per status (Open to
   Awaiting approval) that adds up to her active tickets. The red banner lists
   active **critical** incidents, which everyone sees.
2. **Report incident:** choose IT → Wi-Fi, HQ Tower → Floor 12, seat 12-A-034.
   A warning says Wi-Fi is already reported and recurring at that seat.
3. Pick **Critical** to show the warning that it alerts everyone on site, then
   set it back to **High**. Pick two or three **seats** to show one report
   covering a row of desks. Submit, or cancel.
4. **Incidents:** each status shows how long the ticket has been in it. On a
   ticket, Dana can't add notes, change priority or close it; she can edit the
   description only while it is Open, and ask to reopen a resolved ticket.

### 2. Engineer (Priya): work the ticket – about 1½ minutes
1. **Dashboard:** all her tickets, a tile for each status (they add up), the
   unassigned pool, her shift, hours logged and missed commitments.
2. **Incidents → Unassigned** (the default tab is *My tickets*, which only shows
   tickets she is on). A ticket Dana just reported is at the top.
3. **Take this ticket.** If two engineers click at once, the database lets only
   one become primary; the other joins as a helper.
4. **Acknowledge for my shift → Start work → Resolve** (needs a note) **→ Close
   ticket.** Closing asks an admin to approve.
5. Optional: the **Work log** tab records labor hours (at most 12 a day across
   all tickets); **Take / join selected** takes several tickets at once.

### 3. Admin (Alex): see everything and act – about 4 minutes
1. **Dashboard:** total reported (active, archived, voided), then a section per
   business question: open incidents, what needs attention, recurring
   locations, response times, engineer workload, common issues and how well
   employees are kept informed.
2. **Engineers:** switch Priya to unavailable. She is flagged **Needs reassignment**.
3. Open one of her tickets and click **Reassign**. The list suggests the best
   available engineer (specialty, then on shift, then workload). Check the
   **History** tab.
4. Back on **Engineers**, click **Priya Nair** to see every ticket she is on,
   including the one just reassigned off her.
5. Click Lena Ortiz's red **4 missed shifts** chip: each missed commitment with
   its ticket, the shift, and the status then and now.
6. **Incidents:** search **#14** to jump to a ticket by number. Switch on
   **Archived** and open **#38** to see a voided ticket.
7. **Approvals:** tick requests and **Approve** or **Reject** several at once.
8. **People:** make Tom Becker an admin, then an engineer again. Role changes
   apply on the person's next click.

**Afterwards:** switch Priya back to available and check Tom is an engineer.

## Things to know

- Changes you make in the demo are real: they stay in the live database for the
  next person. Avoid voiding or approving tickets you want to keep showing.
- Lena's four missed shifts come from the seed data (tickets #14 to #17). If
  those tickets are resolved, the missed-shift demo changes.
- Pages refresh every 30 seconds, so a change made in one browser appears in the
  others without reloading.
