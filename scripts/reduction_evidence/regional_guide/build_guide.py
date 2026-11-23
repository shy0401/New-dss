"""지역 기후 가이드 표: 기상청 평년값(1991~2020) → 지점 기후 값 → 시군구(설계기준 지역 구분 269곳) → 기준 배출 방향 가이드.
규칙은 README '규칙'(결과를 보기 전에 적음). 읽기만 하고 원본을 고치지 않는다.

usage: python -E -P build_guide.py <kma_normals dir> <Carbon-Urban-DSS/backend/reference dir> <out dir>
"""
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
kma, ref, out = (Path(a) for a in sys.argv[1:4])
out.mkdir(parents=True, exist_ok=True)
HDD_BASE, CDD_BASE = 18.0, 24.0          # 기준 문서 5.10
EF_E, EF_G = 0.433, 0.1819               # 기준 문서 5.4 · 5.5
REF_NAME = "전주"                       # 기준 지역(이 자료의 지점 번호는 ASOS와 다름: 전주 864)
METRO = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
         "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종"}
OFFICIAL_SOUTH = 153.34 / 173.99 - 1     # 표준베이스라인 개별난방 아파트 남부 ÷ 중부2 − 1


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# 1. 지점 값 ------------------------------------------------------------------
days = defaultdict(dict)                 # stn -> (mm,dd) -> record
names = {}
files = sorted((kma / "daily").glob("*.json"))
for f in files:
    mm, dd = (int(x) for x in f.stem.split("-"))
    for r in json.loads(f.read_text(encoding="utf-8"))["dataList"]:
        days[r["stnId"]][(mm, dd)] = r
        names[r["stnId"]] = r["stnNm"]
n_days = len(files)
stations = {}
for stn, recs in days.items():
    ta = [num(r.get("avgTa")) for r in recs.values()]
    if len(recs) < n_days or any(v is None for v in ta):
        hdd = cdd = summer = winter = None
    else:
        hdd = sum(max(0.0, HDD_BASE - v) for v in ta)
        cdd = sum(max(0.0, v - CDD_BASE) for v in ta)
        summer = statistics.mean(num(r["avgTa"]) for (m, _), r in recs.items() if m in (6, 7, 8))
        winter = statistics.mean(num(r["avgTa"]) for (m, _), r in recs.items() if m in (12, 1, 2))
    ss = [num(r.get("sumSsHr")) for r in recs.values()]
    sun = sum(ss) if len(recs) == n_days and all(v is not None for v in ss) else None
    rh = [num(r.get("avgRhm")) for (m, _), r in recs.items() if m in (6, 7, 8)]
    rh_s = statistics.mean(rh) if rh and all(v is not None for v in rh) else None
    stations[stn] = {"stn": stn, "name": names[stn], "hdd": hdd, "cdd": cdd, "summer": summer, "winter": winter, "sun": sun, "rh_summer": rh_s}
REF_STN = min(s for s, st in stations.items() if st["name"] == REF_NAME)
refv = stations[REF_STN]

# 2. 전주 몫 · 배출 몫 ------------------------------------------------------------
cond = {r["sigungu_code"]: r for r in csv.DictReader(open(ref / "regional_conditions_sigungu.csv", encoding="utf-8-sig"))}
jj = [cond[c] for c in ("52111", "52113") if c in cond]
mean = lambda k: statistics.mean(float(r[k]) for r in jj if r[k])
s_cool, s_heat_e, s_heat_g = mean("elec_share_cool_median"), mean("elec_share_heat_median"), mean("gas_share_heat_median_v2")
e_kwh, g_kwh = mean("stat2025_apt_electricity_kwh_per_m2"), mean("stat2025_apt_citygas_kwh_per_m2")
e_c, g_c = e_kwh * EF_E, g_kwh * EF_G
w_e, w_g = e_c / (e_c + g_c), g_c / (e_c + g_c)          # 배출 몫
k_e, k_g = e_kwh / (e_kwh + g_kwh), g_kwh / (e_kwh + g_kwh)   # 에너지 몫


def guide(st):
    if st["hdd"] is None or not refv["hdd"]:
        return None, None, None
    rh_, rc_ = st["hdd"] / refv["hdd"], (st["cdd"] / refv["cdd"] if refv["cdd"] else None)
    if rc_ is None:
        return None, None, None
    de = s_cool * (rc_ - 1) + s_heat_e * (rh_ - 1)
    dg = s_heat_g * (rh_ - 1)
    return de, dg, (w_e * de + w_g * dg, k_e * de + k_g * dg)


# 3. 지점 → 시군구 -------------------------------------------------------------
zones = list(csv.DictReader(open(ref / "design_zone_sigungu.csv", encoding="utf-8-sig")))
def base(token):
    return re.sub(r"(시|군|구)$", "", token)


by_name = defaultdict(list)
for stn, st in stations.items():
    # 지점 이름은 끝의 '시' · '군'만 뗀다(README 규칙). '구'까지 떼면 '대구'가 '대'가 됨(첫 실행에서 대구 9곳이 빠진 버그)
    nm = "광주(경기)" if st["name"] == "경기광주" else re.sub(r"(시|군)$", "", st["name"])
    by_name[nm].append(stn)


rows, stn_sido = [], {}
for z in zones:
    sido, full = z["sido_name"], z["sigungu_name"]
    rest = full[len(sido):].strip().split() if full.startswith(sido) else full.split()[1:]
    # README 규칙 1 덧붙임(2026-11-21): 시 이름으로 시작하는 지점이 하나뿐이고 좌표가 그 시 안(DB 경계로 확인)이면 그 시 지점.
    # 좌표 확인은 DB에서 했고(README 기록), 여기서는 확인된 지점 번호만 받는다.
    COORD_CHECKED = {"세종": "611"}
    starts = [s for s, st in stations.items() if sido in METRO and st["name"].startswith(METRO[sido]) and st["name"] != METRO[sido]]
    if sido in METRO and METRO[sido] in by_name:
        stn, how = min(by_name[METRO[sido]]), "광역시 지점"
    elif sido in METRO and len(starts) == 1 and str(starts[0]) == COORD_CHECKED.get(METRO[sido]):
        stn, how = starts[0], "광역시 이름 지점(좌표 확인)"
    elif rest and sido not in METRO and (key := ("광주(경기)" if sido == "경기도" and base(rest[0]) == "광주" else base(rest[0]))) in by_name:
        stn, how = min(by_name[key]), "지점 있음"
    else:
        stn, how = None, None
    if stn is not None:
        stn_sido.setdefault(stn, (sido, z["design_zone"]))
    rows.append({"z": z, "stn": stn, "how": how})
for r in rows:
    if r["stn"] is None:
        sido, zone = r["z"]["sido_name"], r["z"]["design_zone"]
        cand = [s for s, (sd, zn) in stn_sido.items() if sd == sido and zn == zone]
        if cand:
            r["stn"], r["how"] = min(cand), "같은 시도 · 같은 지역 구분 대표 지점"
        else:
            cand = [s for s, (sd, _) in stn_sido.items() if sd == sido]
            if cand:
                r["stn"], r["how"] = min(cand), "같은 시도 대표 지점"

# 우리 단지 자료가 있는 시군구의 평년값 HDD 범위(규칙 5)
db_codes = set(cond)
db_hdd = [stations[r["stn"]]["hdd"] for r in rows if r["z"]["sigungu_code"] in db_codes and r["stn"] and stations[r["stn"]]["hdd"]]
lo, hi = (min(db_hdd), max(db_hdd)) if db_hdd else (None, None)

# 4. 다른 요소: 지자체 건물 부문 과제 수(시도 · 시) -------------------------------
plans = list(csv.DictReader(open(ref / "local_plans_building.csv", encoding="utf-8-sig")))
plan_n = defaultdict(int)
for p in plans:
    plan_n[p["지역_코드"]] += 1

fmt = lambda v, d=0: "" if v is None else f"{v:.{d}f}"
out_rows = []
for r in rows:
    z, st = r["z"], stations.get(r["stn"]) if r["stn"] else None
    de = dg = None
    dc = dk = None
    if st:
        de, dg, both = guide(st)
        if both:
            dc, dk = both
    code = z["sigungu_code"]
    out_rows.append({
        "sigungu_code": code, "sigungu_name": z["sigungu_name"], "design_zone": z["design_zone"],
        "station_id": r["stn"] or "", "station_name": st["name"] if st else "", "mapping": r["how"] or "",
        "hdd18_normal": fmt(st and st["hdd"]), "cdd24_normal": fmt(st and st["cdd"], 1),
        "hdd_ratio_vs_jeonju": fmt(st and st["hdd"] and st["hdd"] / refv["hdd"], 3),
        "cdd_ratio_vs_jeonju": fmt(st and st["cdd"] is not None and refv["cdd"] and st["cdd"] / refv["cdd"], 3),
        "summer_mean_c": fmt(st and st["summer"], 1), "winter_mean_c": fmt(st and st["winter"], 1),
        "sunshine_hours_year": fmt(st and st["sun"]), "summer_rh_pct": fmt(st and st["rh_summer"], 1),
        "guide_electricity_change_pct": fmt(de and de * 100, 1), "guide_gas_change_pct": fmt(dg and dg * 100, 1),
        "guide_energy_change_pct": fmt(dk and dk * 100, 1), "guide_emission_change_pct": fmt(dc and dc * 100, 1),
        "within_our_data_hdd_range": "" if not (st and st["hdd"] and lo) else ("예" if lo <= st["hdd"] <= hi else "아니오(자료 범위 밖)"),
        "local_plan_tasks_sido": plan_n.get(code[:2], "") , "local_plan_tasks_city": plan_n.get(code, ""),
        "value_kinds": "zone=OBSERVED(고시); climate=기상청 평년값(1991~2020) 지점 값; degree days=CALCULATED(평년 일평균, 지역 간 비로만); guide=ESTIMATED(전주 용도 몫 · 2025 통계 원단위 · 배출계수로 낸 방향 가이드, 예측 아님, 가스 몫은 분해 관문 못 넘은 참고값)",
    })
with open(out / "regional_climate_guide.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
    w.writeheader()
    w.writerows(out_rows)

# 5. 점검(규칙 6) ---------------------------------------------------------------
south = [float(r["guide_energy_change_pct"]) for r in out_rows if r["design_zone"] == "남부" and r["guide_energy_change_pct"] != ""]
jb2 = [float(r["guide_energy_change_pct"]) for r in out_rows if r["design_zone"] == "중부2" and r["guide_energy_change_pct"] != ""]
summary = {
    "days": n_days, "stations": len(stations), "ref": refv,
    "jeonju_shares": {"elec_cool": s_cool, "elec_heat": s_heat_e, "gas_heat_v2": s_heat_g, "elec_kwh_m2": e_kwh, "gas_kwh_m2": g_kwh,
                      "emission_share_elec": w_e, "energy_share_elec": k_e},
    "mapping": {k: sum(1 for r in rows if r["how"] == k) for k in ("광역시 지점", "광역시 이름 지점(좌표 확인)", "지점 있음", "같은 시도 · 같은 지역 구분 대표 지점", "같은 시도 대표 지점", None)},
    "db_hdd_range_normals": [lo, hi],
    "check_south": {"our_energy_median_pct": statistics.median(south) if south else None,
                    "jungbu2_energy_median_pct": statistics.median(jb2) if jb2 else None,
                    "official_south_vs_jungbu2_pct": OFFICIAL_SOUTH * 100},
}
if south and jb2:
    ours = ((1 + statistics.median(south) / 100) / (1 + statistics.median(jb2) / 100) - 1) * 100
    summary["check_south"]["our_south_vs_jungbu2_pct_supplementary"] = ours   # 보조: 중부2 중앙값 대비
    # 규칙 6(주 판정): 남부 지점 에너지 변화율 중앙값(전주 대비)을 정부 남부 ÷ 중부2와 견줌
    summary["check_south"]["within_5pp"] = abs(statistics.median(south) - OFFICIAL_SOUTH * 100) <= 5
(out / "guide_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1, default=str)[:2500])
