"""salary immutability + append-only triggers

Implements the remaining database-enforced invariants from
docs/02_DATABASE.md section 18:

* DB-13 ``trg_salary_records_finalized_immutable`` - a FINALIZED/PAID salary
  record may not have its financial inputs or computed amounts edited; the only
  permitted transitions are FINALIZED -> PAID (plus paid_at/paid_by/notes).
* DB-15 ``trg_audit_logs_append_only`` - audit rows cannot be altered/removed.
* DB-18 ``trg_ledger_entries_append_only`` - ledger rows are append-only;
  corrections are new rows carrying ``reverses_entry_id``.

Revision ID: b7d1e9c4a2f0
Revises: d2f7c0d44e85
Create Date: 2026-09-25 18:05:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "b7d1e9c4a2f0"
down_revision = "d2f7c0d44e85"
branch_labels = None
depends_on = None


SALARY_FN = """
CREATE OR REPLACE FUNCTION fn_salary_records_finalized_immutable()
RETURNS trigger AS $$
DECLARE
    mutable text[] := ARRAY['status', 'paid_at', 'paid_by', 'locked_at', 'notes',
                            'version', 'updated_at'];
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status IN ('FINALIZED', 'PAID') THEN
            RAISE EXCEPTION 'Finalized salary record % cannot be deleted', OLD.id
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.status IN ('FINALIZED', 'PAID') THEN
        IF (to_jsonb(NEW) - mutable) IS DISTINCT FROM (to_jsonb(OLD) - mutable) THEN
            RAISE EXCEPTION 'Finalized salary record % is immutable', OLD.id
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF OLD.status = 'PAID' AND NEW.status <> 'PAID' THEN
            RAISE EXCEPTION 'Paid salary record % cannot change status', OLD.id
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF NEW.status NOT IN ('FINALIZED', 'PAID') THEN
            RAISE EXCEPTION 'Salary record % status may only advance to PAID', OLD.id
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION fn_append_only_guard()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (% is not permitted)', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(SALARY_FN)
    op.execute(
        "CREATE TRIGGER trg_salary_records_finalized_immutable "
        "BEFORE UPDATE OR DELETE ON salary_records "
        "FOR EACH ROW EXECUTE FUNCTION fn_salary_records_finalized_immutable()"
    )

    op.execute(APPEND_ONLY_FN)
    op.execute(
        "CREATE TRIGGER trg_audit_logs_append_only "
        "BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION fn_append_only_guard()"
    )
    op.execute(
        "CREATE TRIGGER trg_ledger_entries_append_only "
        "BEFORE UPDATE OR DELETE ON employee_ledger_entries "
        "FOR EACH ROW EXECUTE FUNCTION fn_append_only_guard()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_append_only ON employee_ledger_entries")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_salary_records_finalized_immutable ON salary_records")
    op.execute("DROP FUNCTION IF EXISTS fn_append_only_guard()")
    op.execute("DROP FUNCTION IF EXISTS fn_salary_records_finalized_immutable()")