# 원문 대조 D 묶음(서울 11 · 광주 29) 공통: 표 쓰기와 앞선 표와의 차이 목록 만들기.
# 원문 PDF는 읽기만 한다. 이 파일은 CSV만 쓴다.
import csv
import re
from pathlib import Path

HERE = Path(__file__).parent
# 앞선 행은 묶음 원자료(plans_group1.csv, 2026-11-20 01:34 그대로)에서 읽는다.
# 합친 표(local_plans_building.csv)는 메인이 원문 대조 결과를 다시 합치면서 바뀌므로 견줄 기준으로 쓰지 않는다.
OLD = HERE.parent / "plans_group1.csv"

COLS = ["지역_코드", "지역", "계획_이름", "계획_기간", "수립_시기", "부문", "과제_번호", "과제_이름",
        "과제_내용", "수단_ID", "층", "대상", "목표_감축량", "목표_단위", "목표_연도", "실적_2025",
        "예산", "지원_제도", "출처_주소", "쪽", "본_범위", "값의_종류", "비고"]
# 지역 전체에 같은 값이 들어가는 열(차이는 한 줄로만 적는다)
REGION_COLS = ["지역", "계획_이름", "계획_기간", "수립_시기", "출처_주소", "본_범위", "값의_종류"]
ROW_COLS = [c for c in COLS if c not in REGION_COLS and c != "지역_코드"]
CH_COLS = ["지역_코드", "과제_번호", "과제_이름", "열", "앞선_값", "원문_값", "쪽", "종류", "비고"]

MEASURES = {"new_build_package", "retrofit_package", "insulation", "window", "rooftop_pv",
            "solar_thermal_geothermal_fuelcell", "heat_pump", "heat_source_district",
            "boiler_heating_control", "lighting_appliance_elevator", "bems_metering", "operation",
            "greenery", "materials_other", "other"}


def old_rows(code):
    with open(OLD, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["지역_코드"] == code]
    for r in rows:  # 합친 표와 같은 띄어쓰기(merge_plans.py의 층 표기 규칙)로 맞춰 띄어쓰기만 다른 칸을 세지 않는다
        r["층"] = re.sub(r"\s*·\s*", " · ", r["층"])
    return rows


def check_rows(rows):
    for r in rows:
        assert set(r) == set(COLS), set(r) ^ set(COLS)
        for m in r["수단_ID"].split(";"):
            assert m in MEASURES, (r["과제_번호"], m)
        assert r["값의_종류"] == "지자체 계획값(자체 평가)"
        assert r["본_범위"].startswith("전문(원문 PDF 글자, 읽은 쪽:")
        for c in COLS:
            assert "\n" not in r[c]


def write_plans(code, rows):
    check_rows(rows)
    p = HERE / f"plans_{code}.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return p


def target_text(r):
    if r["목표_감축량"] == "":
        return "감축량 없음"
    return f"{r['목표_감축량']} {r['목표_단위']}({r['목표_연도']})"


def make_changes(code, rows, match, removed_notes, added_note="", cell_notes=None):
    """match: {새 과제_번호: 앞선 행의 과제_이름(앞선 표에서 그 지역 안에 하나뿐인 이름)}.
    removed_notes: {앞선 과제_이름: 지운 까닭}."""
    old = old_rows(code)
    by_name = {r["과제_이름"]: r for r in old}
    assert len(by_name) == len(old)
    out = []
    # 지역 전체 열
    for c in REGION_COLS:
        ov = sorted({r[c] for r in old})
        nv = sorted({r[c] for r in rows})
        if ov != nv:
            out.append({"지역_코드": code, "과제_번호": "(모든 행)", "과제_이름": "(지역 전체 열)", "열": c,
                        "앞선_값": " / ".join(ov), "원문_값": " / ".join(nv), "쪽": "",
                        "종류": "값 고침", "비고": "지역의 모든 행에 같은 값"})
    used = set()
    n_cell = n_add = 0
    for r in rows:
        key = r["과제_번호"]
        if key in match:
            o = by_name[match[key]]
            used.add(match[key])
            for c in ROW_COLS:
                if o[c] != r[c]:
                    if c == "수단_ID":
                        kind = "수단 고침"
                    elif o[c] == "":
                        kind = "빈칸 채움"
                    else:
                        kind = "값 고침"
                    note = ""
                    if r[c] == "":
                        note = "원문에 그 값이 없어 비움"
                    elif cell_notes and c in cell_notes:
                        note = cell_notes[c]
                    out.append({"지역_코드": code, "과제_번호": key, "과제_이름": r["과제_이름"], "열": c,
                                "앞선_값": o[c], "원문_값": r[c], "쪽": r["쪽"], "종류": kind, "비고": note})
                    n_cell += 1
        else:
            out.append({"지역_코드": code, "과제_번호": key, "과제_이름": r["과제_이름"], "열": "(행 전체)",
                        "앞선_값": "", "원문_값": target_text(r), "쪽": r["쪽"], "종류": "행 추가", "비고": added_note})
            n_add += 1
    n_del = 0
    for o in old:
        if o["과제_이름"] not in used:
            out.append({"지역_코드": code, "과제_번호": o["과제_번호"], "과제_이름": o["과제_이름"], "열": "(행 전체)",
                        "앞선_값": "행 있음(앞선 쪽: " + o["쪽"] + ")", "원문_값": "", "쪽": "",
                        "종류": "행 삭제", "비고": removed_notes[o["과제_이름"]]})
            n_del += 1
    assert set(removed_notes) == {o["과제_이름"] for o in old} - used
    p = HERE / f"changes_{code}.csv"
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CH_COLS)
        w.writeheader()
        w.writerows(out)
    n_region = sum(1 for x in out if x["과제_번호"] == "(모든 행)")
    return {"앞선 행": len(old), "새 행": len(rows), "맞댄 행": len(used), "고친 칸(과제 열)": n_cell,
            "고친 칸(지역 전체 열)": n_region, "행 추가": n_add, "행 삭제": n_del, "changes 줄": len(out)}
