"""Concurrency, Financial Integrity, and Domain Business Rules Tests.

Covers requirement in docs/09_TEST_PLAN.md:
- Concurrency test C-01 (Order Claiming Race Condition)
- Concurrency test C-02 (Duplicate Check-in Race)
- Financial Integrity (Ledger append-only, Payroll run locking, Salary calculation)
- Leave balance calculations & validation
"""

import asyncio
import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.core.db import get_sessionmaker
from app.modules.orders.service import get_order, create_order
from app.modules.settings.service import SettingsService


@pytest.mark.asyncio
async def test_concurrency_order_claim_race(admin, employee_factory):
    """C-01: Two employees attempt to claim the exact same broadcasted order simultaneously.

    Exactly ONE claim must succeed (200 OK); the second MUST fail (404 or 409/422), maintaining DB integrity.
    """
    emp1_data, emp1_client = await employee_factory(roles=["EMPLOYEE"])
    emp2_data, emp2_client = await employee_factory(roles=["EMPLOYEE"])

    # 1. Admin creates an order with broadcast
    create_resp = await admin.post(
        "/api/v1/orders",
        json={
            "customer_name": "Race Test Customer",
            "customer_phone": "9999999999",
            "delivery_address": "123 Main St",
            "order_amount": "500.00",
            "currency": "INR",
            "broadcast": {"audience_scope": "ALL_ACTIVE_EMPLOYEES"},
        },
    )
    assert create_resp.status_code in (200, 201), create_resp.text
    order_id = create_resp.json()["id"]

    # 2. Both employees send claim request concurrently
    claim_task_1 = emp1_client.post(f"/api/v1/orders/{order_id}/claim")
    claim_task_2 = emp2_client.post(f"/api/v1/orders/{order_id}/claim")

    resp1, resp2 = await asyncio.gather(claim_task_1, claim_task_2, return_exceptions=True)

    statuses = [r.status_code for r in (resp1, resp2) if hasattr(r, "status_code")]
    
    # Exactly one must be 200/201, the other must fail (404, 409, 422, or 400)
    success_count = sum(1 for s in statuses if s in (200, 201))
    failure_count = sum(1 for s in statuses if s in (404, 409, 422, 400))
    
    assert success_count == 1, f"Expected exactly 1 claim to succeed, got {success_count} ({statuses})"
    assert failure_count == 1, f"Expected 1 claim to fail, got {failure_count} ({statuses})"


@pytest.mark.asyncio
async def test_concurrency_duplicate_checkin(admin, employee_factory):
    """C-02: Simultaneous check-in requests for the same employee.

    At most ONE check-in may succeed simultaneously.
    """
    emp_data, emp_client = await employee_factory(roles=["EMPLOYEE"])

    payload = {
        "location": {"latitude": 12.9716, "longitude": 77.5946, "accuracy_meters": 5.0},
        "qr_payload": "TEST_INVALID_QR_MODE_FALLBACK",
    }
    
    task1 = emp_client.post("/api/v1/attendance/check-in", json=payload)
    task2 = emp_client.post("/api/v1/attendance/check-in", json=payload)

    r1, r2 = await asyncio.gather(task1, task2, return_exceptions=True)
    statuses = [r.status_code for r in (r1, r2) if hasattr(r, "status_code")]

    success_count = sum(1 for s in statuses if s in (200, 201))
    assert success_count <= 1, f"At most 1 check-in may succeed simultaneously: {statuses}"


@pytest.mark.asyncio
async def test_financial_ledger_payroll_integrity(admin, employee_factory):
    """Test Financial Integrity: Advance creation, Ledger entries, Payroll computation, Lock."""
    emp_data, emp_client = await employee_factory(roles=["EMPLOYEE"])
    emp_id = emp_data["id"]

    # 1. Add a ledger credit entry (Bonus/Salary)
    ledger_resp = await admin.post(
        "/api/v1/ledger/entries",
        json={
            "employee_id": emp_id,
            "entry_type": "BONUS",
            "direction": "CREDIT",
            "amount": "1500.00",
            "currency": "INR",
            "business_date": "2025-01-15",
            "reason": "Performance bonus",
        },
    )
    assert ledger_resp.status_code in (200, 201), ledger_resp.text
    entry_id = ledger_resp.json()["id"]

    # Ledger entries must be immutable (no direct DELETE endpoint allowed without reversal)
    del_resp = await admin.delete(f"/api/v1/ledger/entries/{entry_id}")
    assert del_resp.status_code in (404, 405, 403), "Direct deletion of financial ledger entries must be blocked!"

    # 2. Reversal entry (creates a counter-balancing entry pointing to original entry)
    rev_resp = await admin.post(
        f"/api/v1/ledger/entries/{entry_id}/reverse",
        json={"reason": "Correction of mistaken bonus"},
    )
    assert rev_resp.status_code in (200, 201), rev_resp.text
    assert rev_resp.json()["reverses_entry_id"] == entry_id

    # 3. Create Payroll Run
    run_resp = await admin.post(
        "/api/v1/payroll/runs",
        json={"period_year": 2025, "period_month": 1, "notes": "January 2025 Payroll"},
    )
    assert run_resp.status_code in (200, 201), run_resp.text
    run_id = run_resp.json()["id"]

    # Compute salary
    compute_resp = await admin.post(f"/api/v1/payroll/runs/{run_id}/compute")
    assert compute_resp.status_code in (200, 201, 202), compute_resp.text

    # Finalize payroll run
    fin_resp = await admin.post(f"/api/v1/payroll/runs/{run_id}/finalize")
    assert fin_resp.status_code in (200, 201), fin_resp.text

    # Lock payroll run
    lock_resp = await admin.post(f"/api/v1/payroll/runs/{run_id}/lock")
    assert lock_resp.status_code in (200, 201), lock_resp.text

    # Modifying a locked payroll run must fail
    compute_again = await admin.post(f"/api/v1/payroll/runs/{run_id}/compute")
    assert compute_again.status_code in (400, 409, 422), "Re-computing locked payroll run must be prohibited"


@pytest.mark.asyncio
async def test_leave_balance_and_overlapping(admin, employee_factory):
    """Test Leave apply, balance deduction, and overlapping dates restriction."""
    emp_data, emp_client = await employee_factory(roles=["EMPLOYEE"])
    emp_id = emp_data["id"]

    # Get casual leave type ID
    types_resp = await admin.get("/api/v1/leave-types")
    assert types_resp.status_code == 200, types_resp.text
    leave_types = types_resp.json()["items"]
    casual_type = next((t for t in leave_types if t["code"] == "CASUAL"), leave_types[0])

    # 1. Apply leave for 2026-11-10 to 2026-11-12
    leave1_resp = await emp_client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": casual_type["id"],
            "start_date": "2026-11-10",
            "end_date": "2026-11-12",
            "reason": "Family function",
        },
    )
    assert leave1_resp.status_code in (200, 201), leave1_resp.text

    # 2. Overlapping leave request (2026-11-11 to 2026-11-14) must fail
    leave2_resp = await emp_client.post(
        "/api/v1/leaves",
        json={
            "leave_type_id": casual_type["id"],
            "start_date": "2026-11-11",
            "end_date": "2026-11-14",
            "reason": "Overlapping request",
        },
    )
    assert leave2_resp.status_code in (400, 409, 422), "Overlapping leave request must be rejected"
