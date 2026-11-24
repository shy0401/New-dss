"""Small versioned schema migrations applied after ``create_all``.

``create_all`` creates missing tables but never alters existing ones. Every
schema change to an existing table must be added here as a new, idempotent
version so every team PC and restored backup converges to the same schema.
Applied versions are recorded in ``schema_migrations``.
"""
from __future__ import annotations

from sqlalchemy import text

MIGRATIONS: list[tuple[str, list[str]]] = [
    ("2026092301_baseline", []),
    ("2026092302_energy_grid_month_index", [
        "CREATE INDEX IF NOT EXISTS ix_energy_monthly_grid_ym ON energy_monthly (grid_id, use_ym)",
    ]),
    ("2026092501_collect_missing_and_register", [
        "ALTER TABLE collection_jobs ADD COLUMN IF NOT EXISTS resume_at TIMESTAMPTZ",
        "ALTER TABLE building_register ADD COLUMN IF NOT EXISTS grid_id TEXT",
        "ALTER TABLE building_register ADD COLUMN IF NOT EXISTS approval_year INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_building_register_grid ON building_register (grid_id)",
        "CREATE INDEX IF NOT EXISTS ix_building_register_pnu ON building_register (parcel_code)",
    ]),
    # 2026-10-27: energy_monthly reached 10M rows (전국 건축HUB). The per-year count and sum by 시·군·구 (grid_building_energy,
    # estimates) went through the 7-column unique key and took about a minute each; this index answers them by range.
    # On a large table this runs once at start-up for a few minutes (the PC built it CONCURRENTLY beforehand).
    ("2026102701_energy_sigungu_month_index", [
        "CREATE INDEX IF NOT EXISTS ix_energy_monthly_sgg_ym ON energy_monthly (sigungu_code, use_ym)",
    ]),
    # 2026-11-24: the dashboard's region monthly sums (SUM(usage_kwh) by month and energy type) still read the table
    # for usage_kwh/energy_type (Suwon 3.8 s, the whole table each time). With them in the index the sums and the
    # row counts are answered from the index alone (Suwon 0.3 s). About 1.5 GB at 24M rows; built in ~30 s on the PC
    # (CONCURRENTLY beforehand); a PC without it builds it once at start-up.
    ("2026112401_energy_sigungu_month_type_index", [
        "CREATE INDEX IF NOT EXISTS ix_energy_monthly_sgg_ym_type ON energy_monthly (sigungu_code, use_ym, energy_type) "
        "INCLUDE (usage_kwh, grid_id)",
    ]),
]


def apply_migrations(engine) -> list[str]:
    applied: list[str] = []
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        # Serialize concurrent API/worker startups.
        connection.execute(text("SELECT pg_advisory_xact_lock(2026092301)"))
        done = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
        for version, statements in MIGRATIONS:
            if version in done:
                continue
            for statement in statements:
                connection.execute(text(statement))
            connection.execute(text("INSERT INTO schema_migrations (version) VALUES (:version)"), {"version": version})
            applied.append(version)
    return applied
