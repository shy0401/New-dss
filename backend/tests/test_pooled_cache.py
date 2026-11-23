"""The pooled-baseline memory (service._slim_complexes) must outlive the session that filled it.

2026-11-24: the whole test run failed in test_reporting_api because test_extended_api filled the memory inside a session
that then called db.rollback(). A rollback expires every ORM object of the session, so the remembered ApartmentComplex
objects came back detached and expired and the next request raised DetachedInstanceError on c.heating_type.
"""
import pytest


@pytest.mark.db
def test_slim_complexes_survive_rollback_and_closed_session():
    from app import service
    from app.db import Session
    service._SLIM_COMPLEXES.clear()
    with Session() as db:
        complexes = service._slim_complexes(db)
        db.rollback()  # expires every ORM object the session holds
    if not complexes:
        pytest.skip("no K-apt complexes loaded")
    # a later request (new session) reads the remembered rows: no refresh from the closed session
    with Session() as db:
        again = service._slim_complexes(db)
    assert again is complexes
    first = again[0]
    for name in ("kapt_code", "heating_type", "households", "gross_floor_area_m2", "management_area_m2", "name"):
        getattr(first, name)
    from app.grid_metrics import validated_complex_areas
    areas, _ = validated_complex_areas(again)
    assert len(areas) == len({c.kapt_code for c in again})
    service._SLIM_COMPLEXES.clear()
