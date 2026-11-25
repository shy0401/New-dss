"""원단위 기반 계획 배출의 안내문(2026-11-25): 용도별 줄로 계산했으면 그 원단위를 적고, '한 원단위만'이라고 쓰지 않는다.

발표 전 점검에서 시연 화면(주거 60,000 m² + 상업 20,000 m²)이 값은 용도별(30.23 · 97.96)로 냈는데
안내문은 "한 원단위를 모든 용도에 적용, 용도별 원단위는 쓰지 않았습니다"라고 보였다.
"""
from app.plan_bundle import plan_emission_block


def _effort(lines):
    return {"available": True, "added_floor_area_m2": 80000.0, "removed_floor_area_m2": 0.0, "scope": "전력",
            "basis_label": "공동주택(K-apt 관리비 전력)", "intensity_kwh_per_m2": 30.23, "baseline_year": 2025,
            "new_load_kwh": 3773000.0, "removed_load_kwh": 0.0, "bau_kgco2eq": 1.0,
            "new_load_lines": lines, "removed_load_lines": [],
            "targets": [{"key": "plan_added", "net_added_kwh": 3773000.0, "net_added_kgco2eq": 1633709.0}]}


def test_note_names_the_per_use_intensities_when_lines_were_used():
    lines = [{"use": "residential", "use_label": "주거", "floor_area_m2": 60000.0, "kwh_per_m2": 30.23, "basis": "AREA"},
             {"use": "commercial", "use_label": "상업", "floor_area_m2": 20000.0, "kwh_per_m2": 97.96, "basis": "REGION"}]
    note = plan_emission_block(_effort(lines), [])["intensity_note"]
    assert "용도별 원단위는 쓰지 않았습니다" not in note
    assert "용도별" in note and "주거 30.23" in note and "상업 97.96" in note


def test_note_keeps_the_single_intensity_sentence_without_lines():
    note = plan_emission_block(_effort([]), [])["intensity_note"]
    assert "한 원단위(공동주택(K-apt 관리비 전력) 30.23 kWh/m²·년)를 모든 용도의 계획 연면적에 적용했습니다" in note
