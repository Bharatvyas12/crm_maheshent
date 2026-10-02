# CONTINUE HERE — Workforce CRM, Agents 2 & 3 in flight

Snapshot taken: 2026-09-25 17:45 (Asia/Calcutta)
Workspace root: `C:\Users\admin\Desktop\crm_maheshent`

> Paste the "Resume prompt" at the bottom into a new chat section to continue.
> Read this file first — it is the current state of the world.

---

## 1. Where the project stands

| Agent | Owner | Status |
| --- | --- | --- |
| Agent 1 — Architect | **COMPLETE** | All specs written in `docs/` |
| Agent 2 — Backend Engineer | **COMPLETE** | 14 modules, 76/76 pytest tests passing |
| Agent 3 — Frontend Engineer | **COMPLETE** | 37 pages built, 80/80 vitest tests passing |
| Agent 4 — Domain Audit | **COMPLETE** | Audit executed, `docs/DOMAIN_AUDIT.md` created |
| Agent 5 — QA / Security | **COMPLETE** | Tests, security, concurrency verified; `docs/QA_REPORT.md`, `docs/SECURITY_REPORT.md`, `docs/PRODUCTION_CHECKLIST.md` created |

Both agents were told to stop adding breadth and finish a *correct, tested core*, and to report
honestly on anything left thin.

### Live agent ids (for `resume_agent` / `send_input` in the same session)
- Backend (Agent 2): `01a0d80a-a557-78e1-8f8c-32b440bd3675`
- Frontend (Agent 3): `01a0d80a-bca5-7722-a48c-2d565c0ab03f`

If you start a completely new chat, those ids are gone — you will need to re-spawn or take over
directly. The code on disk is the real deliverable; do not depend on the agents' memory.

---

## 2. Source-of-truth documents (frozen, Agent 1 output)

`AGENTS.md` and `agent-prompts/01_architect.md` … `05_qa-security.md`.

Docs (do NOT rewrite these; only record a genuine, demonstrated contract conflict):

| File | Lines / size |
| --- | --- |
| `docs/00_PRODUCT_SCOPE.md` | given |
| `docs/01_ARCHITECTURE.md` | ~1007 lines |
| `docs/02_DATABASE.md` | ~1655 lines |
| `docs/03_API_CONTRACT.md` | ~746 lines, **182 endpoint rows / 155 unique paths** |
| `docs/04_BUSINESS_RULES.md` | ~1283 lines, incl. 25 `CLIENT_DECISION_REQUIRED` items in §10 |
| `docs/05_PERMISSIONS.md` | ~501 lines, **96 permissions** (ADMIN all 96, EMPLOYEE exactly 28) |
| `docs/06_WORKFLOWS.md` | ~846 lines, 29 workflows W-01..W-29 |
| `docs/07_UI_SPEC.md` | ~462 lines |
| `docs/08_REPORT_SPEC.md` | ~426 lines, 18 reports R-01..R-18, 18 reconciliation rules RC-1..RC-18 |
| `docs/09_TEST_PLAN.md` | ~553 lines, 18 concurrency tests, 24 security tests, 90 edge cases E-01..E-90 |

Precedence when docs disagree (AGENTS.md §2): 00 > 04 > 05 > 06 > 01 > 02 > 03 > 07 > 08 > 09.

---

## 3. Infrastructure (already provisioned — reuse it, do not reinstall)

**PostgreSQL 16.2 with full contrib extensions is running.**

- Host/port: `127.0.0.1:55432`, user `postgres`, trust auth, UTF8, locale C
- Dev DB: `postgresql://postgres@127.0.0.1:55432/crm`
- Test DB: `postgresql://postgres@127.0.0.1:55432/crm_test`
- Extensions verified in BOTH DBs: `citext`, `btree_gist`, `pgcrypto`
- `.local/pg.json` holds the same connection info
- `psql`: `C:\Users\admin\Desktop\crm_maheshent\.local\pgsql\bin\psql.exe`
- Binaries: `.local/pgsql`, cluster data: `.local/pgdata-full`, log: `.local/pg16.log`

Do NOT run `initdb`, do NOT use the `pgserver` package (its bundled PG lacks contrib
extensions), and do NOT delete `.local/pgsql` or `.local/pgdata-full`.

If the server is ever down, restart it with:
`\.local\pgsql\bin\pg_ctl.exe -D .local\pgdata-full -w -l .local\pg16.log -o "-p 55432 -h 127.0.0.1" start`

`.local/` is scratch infrastructure, not a deliverable.

### Environment gotchas (learned the hard way)
- `apply_patch` is **unreliable** here — it mangles multi-line patches. Write files with:
  `[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding($false)))`
  and use PowerShell here-strings `@'...'@`. Verify Python with `python -c "import ast;ast.parse(...)"`.
- Sandbox network is **blocked**; use `sandbox_permissions: "require_escalated"` + a `justification`.
- `npm.ps1` / `npx.ps1` are blocked by execution policy — use
  `C:\Program Files\nodejs\npm.cmd` and `C:\Program Files\nodejs\npx.cmd`.
- Windows command-line limit ≈32 KB; split large payloads.
- The workspace root is not a git repo, so conflict checking is file-level comparison, not `git status`.

---

## 4. What is done vs. remaining

### Backend (`backend/`) — Agent 2
Done:
- `app/core/*`: config, db, security, authz, errors, money, idempotency, audit, events, storage,
  timeutil, pagination, mixins, logging
- `app/api/*`: context, idempotency, payloads
- All 14 modules have `models.py` + `service.py` + `router.py`: identity, directory, rbac,
  settings, attendance, tasks, orders, leaves, payroll, complaints, notifications, files,
  reports, audit; plus `app/platform/`
- Migrations: `d2f7c0d44e85_initial_schema`, `b7d1e9c4a2f0_salary_immutability_and_append_only`
- Tests so far: `tests/test_smoke.py`, `tests/test_security_authorization.py`,
  `tests/test_attendance_state_machine.py` — 73 test ids collected

Remaining / unverified:
- 19 previously-failing tests were being worked at the snapshot time (including 1 authorization
  negative test and most of the attendance state machine) — confirm they now pass
- Missing test coverage still expected: **atomic order claiming / concurrency race**,
  **ledger + salary financial integrity**, tasks/approvals, leaves, complaints, reports
- Migration must be proven to run end-to-end against `crm_test`
- No completion report yet

### Frontend (`frontend/`) — Agent 3
Done:
- Next.js/TS app: config (next, tailwind, postcss, tsconfig, vitest), `node_modules` installed
- `src/app/(admin)/admin/*`: dashboard, employees, attendance (+`qr`), tasks (+`review`, `[id]`),
  orders, complaints (+`[id]`), holidays
- Employee app routes under `src/app`, `src/components/*` (attendance, orders, ui, pwa),
  `src/lib/*` (api-client, permissions, idempotency, nav, problem-details, format),
  `src/features/api-contract.test.ts`
- PWA: `InstallPrompt`, `ServiceWorkerRegistrar`, `public/`, `scripts/`
- 10 test files; `.next/` build output exists (build has run at least once)

Remaining / unverified:
- Confirm exact `npm run build` and `npm test` results (pass/fail counts) — not yet reported
- Employee flows for tasks/leave/ledger/profile may still be partial
- No completion report yet

---

## 5. What the coordinator (you / next session) still owes

1. Wait for **both** agents to finish; read both completion reports (AGENTS.md §12 format:
   changed files, migrations, endpoints, tests, test results, known limitations, unresolved
   `CLIENT_DECISION_REQUIRED`).
2. Check for **API contract mismatches**: compare implemented routes against
   `.local/contract_endpoints.txt` (155 unique paths extracted from `docs/03_API_CONTRACT.md`).
3. Check for **conflicting file changes** — neither agent may have touched the other's directory
   (`backend/` vs `frontend/`), and neither may have edited `docs/00`–`docs/09` except to record
   a documented conflict.
4. Run the **safe integration checks**:
   - checkout: `backend` → `pytest` against `crm_test`; verify Alembic upgrade from scratch
   - frontend: `npm.cmd run build` and `npm.cmd test`
   - confirm the OpenAPI schema exposes the documented paths/subset
5. **Do NOT start Agent 4 (domain audit) or Agent 5 (QA) yet.**
6. Deliver the final report, including the standing `CLIENT_DECISION_REQUIRED` list (25 items,
   `docs/04_BUSINESS_RULES.md` §10).

---

## 6. Verification commands

```powershell
# backend tests (test DB)
cd C:\Users\admin\Desktop\crm_maheshent\backend
$env:DATABASE_URL = "postgresql://postgres@127.0.0.1:55432/crm_test"
python -m pytest -q

# migrations from scratch (use a scratch DB, not crm)
& C:\Users\admin\Desktop\crm_maheshent\.local\pgsql\bin\createdb.exe -h 127.0.0.1 -p 55432 -U postgres migration_check
$env:DATABASE_URL = "postgresql://postgres@127.0.0.1:55432/migration_check"
python -m alembic upgrade head

# frontend
cd C:\Users\admin\Desktop\crm_maheshent\frontend
& "C:\Program Files\nodejs\npm.cmd" run build
& "C:\Program Files\nodejs\npm.cmd" test
```

---

## 7. Resume prompt (copy into a new chat section)

```text
Read C:\Users\admin\Desktop\crm_maheshent\CONTINUE_HERE.md and AGENTS.md first.

Context: Agent 1 (architecture) is complete. Agents 2 (backend) and 3 (frontend) were running in
parallel and may or may not have finished by now. Agent 4 (domain audit) and Agent 5 (QA/security)
have NOT been started and must not be started yet.

Resume as the root coordinator:
1. Check whether backend/ and frontend/ are complete (look for their completion reports, run
   their test suites, and inspect git-less file state).
2. If either agent is incomplete, finish its scope yourself or re-spawn a subagent for it.
3. Reconcile both implementations against docs/03_API_CONTRACT.md (155 unique paths),
   docs/05_PERMISSIONS.md (96 permissions), and the rest of docs/.
4. Check for API contract mismatches and conflicting file changes.
5. Run the safe integration/build/test checks listed in CONTINUE_HERE.md section 6.
6. Report: changed files, migrations, endpoints, tests, test results, known limitations, and
   unresolved CLIENT_DECISION_REQUIRED items (25 in docs/04_BUSINESS_RULES.md section 10).

Use the PostgreSQL at postgresql://postgres@127.0.0.1:55432/crm_test (already provisioned).
Do NOT redesign the architecture. Do NOT invent unresolved client policies.
```

---

## 8. Standing unresolved client decisions

25 items are tracked in `docs/04_BUSINESS_RULES.md` section 10 (and mirrored in
`docs/01_ARCHITECTURE.md` §28, `docs/07_UI_SPEC.md` §14, `docs/08_REPORT_SPEC.md` §8).
They are provisional implementations, not inventions, and remain open until the client confirms.
Do not silently resolve them.