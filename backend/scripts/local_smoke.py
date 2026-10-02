"""Local end-to-end smoke test against a running Workforce CRM backend.

Usage (from the repository root):
    python backend/scripts/local_smoke.py

Requires the API at http://127.0.0.1:8000 with the seeded dev database.
Exits 0 when every check passes, 1 otherwise.
"""
from __future__ import annotations

import asyncio
import base64
import random
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
LAT, LON = "12.971600", "77.594600"  # decimal settings must be sent as strings

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

PASS: list[str] = []
FAIL: list[str] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    line = f"[{'PASS' if ok else 'FAIL'}] {name}"
    if detail and not ok:
        line += f"  :: {str(detail)[:240]}"
    print(line, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def body(resp: httpx.Response):
    try:
        return resp.json()
    except Exception:
        return resp.text


def items(payload):
    """Endpoints return either a list or a paginated {'items': [...]} object."""
    if isinstance(payload, dict):
        return payload.get("items", [])
    return payload if isinstance(payload, list) else []


class Api(httpx.AsyncClient):
    async def request(self, method, url, **kwargs):
        if method.upper() in UNSAFE:
            tok = self.cookies.get("csrf_token")
            if tok:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", tok)
                kwargs["headers"] = headers
        return await super().request(method, url, **kwargs)


async def login(client, username, password):
    return await client.post(f"{BASE}/auth/login", json={"username": username, "password": password})


async def login_ready(client, username, password):
    r = await login(client, username, password)
    data = body(r)
    if r.status_code == 200 and isinstance(data, dict) and data["user"].get("must_change_password"):
        newpw = password + "A1!"
        rr = await client.post(
            f"{BASE}/auth/change-password",
            json={"current_password": password, "new_password": newpw},
        )
        return (newpw, r) if rr.status_code == 204 else (None, rr)
    return (password, r) if r.status_code == 200 else (None, r)


async def section(title: str) -> None:
    print(f"=== {title} ===", flush=True)


async def main() -> int:
    try:
        await run()
    except Exception as exc:  # keep the summary even on an unexpected crash
        record("smoke run completed without crashing", False, f"{type(exc).__name__}: {exc}")
    print()
    print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("Failed checks:")
        for f in FAIL:
            print(f"  - {f}")
    return 1 if FAIL else 0


async def run() -> None:
    async with Api(base_url=BASE, timeout=40.0) as admin, Api(base_url=BASE, timeout=40.0) as emp:
        await section("Auth / RBAC")
        r = await login(admin, "admin", "ChangeMe123!")
        record("admin login", r.status_code == 200, f"{r.status_code} {body(r)}")
        r = await login(emp, "employee", "ChangeMe123!")
        record("employee login", r.status_code == 200, f"{r.status_code} {body(r)}")
        me_admin = body(await admin.get(f"{BASE}/auth/me"))
        record("admin session carries ADMIN role", isinstance(me_admin, dict) and "ADMIN" in (me_admin.get("roles") or []), me_admin.get("roles") if isinstance(me_admin, dict) else me_admin)
        r = await emp.get(f"{BASE}/employees")
        record("authorization: employee blocked from /employees (403)", r.status_code == 403, f"{r.status_code} {body(r)}")

        await section("Directory & Settings")
        employees = items(body(await admin.get(f"{BASE}/employees")))
        emp_id = next((e.get("id") for e in employees if e.get("employee_code") == "EMP001"), None)
        record("admin lists employees", emp_id is not None, str(employees)[:200])
        r = await emp.get(f"{BASE}/me")
        record("employee reads own profile", r.status_code == 200, f"{r.status_code} {body(r)}")
        r = await admin.patch(
            f"{BASE}/settings",
            json={
                "changes": {
                    "attendance.geofence_latitude": LAT,
                    "attendance.geofence_longitude": LON,
                    "security.rate_limit.login_per_minute": 1000,
                    "security.rate_limit.qr_issue_per_minute": 1000,
                    "security.rate_limit.checkin_per_minute": 1000,
                    "security.rate_limit.report_per_minute": 1000,
                    "security.rate_limit.upload_per_minute": 1000,
                },
                "reason": "local smoke test setup: geofence + raise throttles",
            },
        )
        record("admin bulk-updates settings (geofence + throttles)", r.status_code == 200, f"{r.status_code} {body(r)}")

        await section("Attendance (GPS + dynamic QR)")
        r = await admin.post(f"{BASE}/attendance/qr-tokens", json={"purpose": "SHOP_CHECKIN"})
        bad_qr = body(r).get("qr_payload") if r.status_code == 201 else None
        record("admin issues shop QR token", r.status_code == 201 and bool(bad_qr), f"{r.status_code} {body(r)}")
        r = await emp.post(f"{BASE}/attendance/check-in", json={"latitude": 0.0, "longitude": 0.0, "accuracy_meters": 8, "location_captured_at": now_iso(), "qr_token": bad_qr})
        record("check-in rejected outside geofence", r.status_code >= 400, f"{r.status_code} {body(r)}")
        r = await admin.post(f"{BASE}/attendance/qr-tokens", json={"purpose": "SHOP_CHECKIN"})
        qr = body(r).get("qr_payload")
        r = await emp.post(f"{BASE}/attendance/check-in", json={"latitude": float(LAT), "longitude": float(LON), "accuracy_meters": 8, "location_captured_at": now_iso(), "qr_token": qr})
        record("employee check-in accepted inside geofence", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.post(f"{BASE}/attendance/check-in", json={"latitude": float(LAT), "longitude": float(LON), "accuracy_meters": 8, "location_captured_at": now_iso(), "qr_token": qr})
        record("single-use QR cannot be replayed", r.status_code >= 400, f"{r.status_code} {body(r)}")
        r = await emp.get(f"{BASE}/attendance/me/today")
        record("employee reads today attendance", r.status_code == 200, f"{r.status_code} {body(r)}")
        bt = items(body(await emp.get(f"{BASE}/break-types")))
        bt_id = (next((b for b in bt if b.get("code") == "LUNCH"), bt[0]) if bt else {}).get("id")
        r = await emp.post(f"{BASE}/attendance/break/start", json={"break_type_id": bt_id})
        record("employee starts break", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.post(f"{BASE}/attendance/break/end", json={})
        record("employee ends break", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await admin.post(f"{BASE}/attendance/qr-tokens", json={"purpose": "SHOP_CHECKOUT"})
        out_qr = body(r).get("qr_payload")
        r = await emp.post(f"{BASE}/attendance/check-out", json={"latitude": float(LAT), "longitude": float(LON), "accuracy_meters": 8, "location_captured_at": now_iso(), "qr_token": out_qr})
        record("employee check-out accepted", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.get(f"{BASE}/attendance/me/summary")
        record("employee attendance summary", r.status_code == 200, f"{r.status_code} {body(r)}")

        await section("Tasks (assign -> start -> submit -> review)")
        r = await admin.post(f"{BASE}/tasks", json={"title": "Smoke task", "description": "verify lifecycle", "priority": "NORMAL", "employee_ids": [emp_id]})
        task = body(r)
        task_id = task.get("id") if isinstance(task, dict) else None
        record("admin creates + assigns task", r.status_code in (200, 201) and task_id, f"{r.status_code} {task}")
        mine = items(body(await emp.get(f"{BASE}/task-assignments/mine")))
        assignment_id = next((a.get("id") for a in mine if str(a.get("task_id")) == str(task_id)), None)
        record("employee sees task assignment", assignment_id is not None, str(mine)[:200])
        if assignment_id:
            r = await emp.post(f"{BASE}/task-assignments/{assignment_id}/start", json={})
            record("employee starts assignment", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
            r = await emp.post(f"{BASE}/task-assignments/{assignment_id}/submissions", json={"description": "work done"})
            sub = body(r)
            sub_id = sub.get("id") if isinstance(sub, dict) else None
            record("employee submits task", r.status_code in (200, 201) and sub_id, f"{r.status_code} {sub}")
            record("admin lists submissions", (await admin.get(f"{BASE}/task-submissions")).status_code == 200)
            if sub_id:
                r = await admin.post(f"{BASE}/task-submissions/{sub_id}/approve", json={"review_notes": "smoke approved"})
                record("admin approves submission", r.status_code in (200, 201), f"{r.status_code} {body(r)}")

        await section("Orders (broadcast -> claim -> status -> POD)")
        r = await admin.post(f"{BASE}/orders", json={"customer_name": "Smoke Customer", "delivery_address": "1 Test Street", "item_summary": "2 boxes", "item_count": 2, "order_amount": "500.00"})
        o = body(r)
        oid = o.get("id") if isinstance(o, dict) else None
        record("admin creates order", oid is not None, str(o)[:200])
        r = await admin.post(f"{BASE}/orders/{oid}/broadcast", json={})
        record("admin broadcasts order", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        avail = items(body(await emp.get(f"{BASE}/orders/available")))
        record("employee sees broadcast order", any(str(x.get("id")) == str(oid) for x in avail), str(avail)[:200])
        r = await emp.post(f"{BASE}/orders/{oid}/claim", json={})
        record("employee claims order", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.post(f"{BASE}/files", data={"purpose": "ORDER_DELIVERY_PROOF", "entity_type": "order", "entity_id": str(oid)}, files={"file": ("pod.png", PNG, "image/png")})
        proof = body(r)
        proof_id = proof.get("id") if isinstance(proof, dict) else None
        record("employee uploads POD photo", r.status_code in (200, 201) and proof_id, f"{r.status_code} {proof}")
        for st in ["PACKING", "PACKED", "READY_FOR_DELIVERY", "OUT_FOR_DELIVERY"]:
            r = await emp.post(f"{BASE}/orders/{oid}/status", json={"to_status": st})
            record(f"order transition -> {st}", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.post(f"{BASE}/orders/{oid}/status", json={"to_status": "DELIVERED", "proof_file_ids": [proof_id] if proof_id else []})
        record("order transition -> DELIVERED (with POD)", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await admin.get(f"{BASE}/orders/{oid}/history")
        record("admin reads order status history", r.status_code == 200, f"{r.status_code} {body(r)}")

        await section("Concurrency: two employees race for one order")
        suffix = uuid.uuid4().hex[:6]
        racer = f"smoke_{suffix}"
        r = await admin.post(f"{BASE}/employees", json={"employee_code": f"EMP{suffix.upper()}", "full_name": "Smoke Racer", "username": racer, "email": f"{racer}@example.com", "date_of_joining": "2025-01-01", "initial_password": "Employee123!", "roles": ["EMPLOYEE"]})
        record("admin creates a second employee", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        async with Api(base_url=BASE, timeout=40.0) as emp2:
            pw2, lr = await login_ready(emp2, racer, "Employee123!")
            record("second employee can log in", pw2 is not None, f"{getattr(lr, 'status_code', None)} {body(lr)}")
            if pw2 is not None:
                r = await admin.post(f"{BASE}/orders", json={"customer_name": "Race Customer", "order_amount": "100.00"})
                oid2 = body(r).get("id")
                await admin.post(f"{BASE}/orders/{oid2}/broadcast", json={})
                r1, r2 = await asyncio.gather(
                    emp.post(f"{BASE}/orders/{oid2}/claim", json={}),
                    emp2.post(f"{BASE}/orders/{oid2}/claim", json={}),
                )
                winners = sum(1 for x in (r1, r2) if x.status_code in (200, 201))
                record("exactly one concurrent claim wins", winners == 1, f"emp={r1.status_code} emp2={r2.status_code}")

        await section("Leaves")
        lts = items(body(await emp.get(f"{BASE}/leave-types")))
        lt_id = lts[0]["id"] if lts else None
        record("employee lists leave types", lt_id is not None, str(lts)[:200])
        if lt_id:
            d = date.today() + timedelta(days=45 + random.randint(0, 280))
            r = await emp.post(f"{BASE}/leaves", json={"leave_type_id": lt_id, "start_date": str(d), "end_date": str(d), "reason": "smoke leave"})
            lv = body(r)
            lid = lv.get("id") if isinstance(lv, dict) else None
            record("employee applies for leave", r.status_code in (200, 201) and lid, f"{r.status_code} {lv}")
            if lid:
                r = await admin.post(f"{BASE}/leaves/{lid}/approve", json={"decision_notes": "smoke approved"})
                record("admin approves leave", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.get(f"{BASE}/leave-balances/mine")
        record("employee reads leave balances", r.status_code == 200, f"{r.status_code} {body(r)}")

        await section("Ledger / Money")
        r = await admin.post(f"{BASE}/ledger/entries", json={"employee_id": emp_id, "entry_type": "BONUS", "amount": "1000.00", "reason": "smoke bonus"})
        record("admin posts ledger entry", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        r = await emp.get(f"{BASE}/ledger/me")
        record("employee reads own ledger", r.status_code == 200, f"{r.status_code} {body(r)}")
        r = await admin.get(f"{BASE}/ledger/balance/{emp_id}")
        record("admin reads ledger balance", r.status_code == 200, f"{r.status_code} {body(r)}")

        await section("Complaints")
        cats = items(body(await emp.get(f"{BASE}/complaint-categories")))
        cat_id = cats[0]["id"] if cats else None
        if cat_id:
            r = await emp.post(f"{BASE}/complaints", json={"category_id": cat_id, "title": "Smoke complaint", "description": "local smoke test"})
            c = body(r)
            cid = c.get("id") if isinstance(c, dict) else None
            record("employee files complaint", r.status_code in (200, 201) and cid, f"{r.status_code} {c}")
            if cid:
                r = await admin.post(f"{BASE}/complaints/{cid}/resolve", json={"resolution_summary": "resolved in smoke test"})
                record("admin resolves complaint", r.status_code in (200, 201), f"{r.status_code} {body(r)}")
        record("admin lists complaints", (await admin.get(f"{BASE}/complaints")).status_code == 200)

        await section("Reports / Notifications / Audit")
        for rep in ["dashboard-summary", "attendance", "work-hours", "tasks", "orders", "leaves", "ledger", "complaints"]:
            r = await admin.get(f"{BASE}/reports/{rep}")
            record(f"report /{rep}", r.status_code == 200, f"{r.status_code} {body(r)}")
        r = await admin.get(f"{BASE}/reports/salary", params={"period_year": date.today().year, "period_month": date.today().month})
        record("report /salary", r.status_code == 200, f"{r.status_code} {body(r)}")
        r = await emp.get(f"{BASE}/notifications/unread-count")
        record("employee notification unread count", r.status_code == 200, f"{r.status_code} {body(r)}")
        r = await admin.get(f"{BASE}/audit-logs")
        record("admin reads audit logs", r.status_code == 200, f"{r.status_code} {body(r)}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
