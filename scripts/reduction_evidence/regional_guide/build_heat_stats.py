"""시군구 아파트 에너지 통계(건물에너지사용량통계 2025, 그린투게더 화면 옮겨 적은 표) → 저장소 참조 표 (2026-11-20).
규칙(결과 전에 적음): 값은 통계 TOE 그대로, "-"였던 칸은 빈칸(NULL). 지역난방 열 비중 = 지역난방 TOE ÷ 아파트 전체 TOE × 100
(같은 통계 같은 단위라 kWh 환산 가정이 필요 없음). 지역난방 TOE가 빈칸이면 비중도 빈칸(0 %로 쓰지 않음). 시군구 코드를
찾지 못한 행(인천 중구 · 동구 · 서구, 행정구역 개편)은 넣지 않고 개수만 알린다.
usage: python -E -P build_heat_stats.py <greentogether_apt_2025.csv> <out.csv>
"""
import csv
import sys

src, out = sys.argv[1:3]
rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
cols = ["sigungu_code", "sigungu_name", "design_zone", "year", "apartment_buildings", "floor_area_m2",
        "electricity_toe", "citygas_toe", "district_heat_toe", "total_toe", "district_heat_share_pct", "value_kinds"]
kept, skipped = [], []
for r in rows:
    if not r["sigungu_code"]:
        skipped.append(f"{r['stat_sido']} {r['stat_sigungu']}")
        continue
    dh, total = r["district_heat_toe"], r["total_toe"]
    share = f"{float(dh) / float(total) * 100:.1f}" if dh and total and float(total) > 0 else ""
    kept.append({"sigungu_code": r["sigungu_code"], "sigungu_name": r['stat_sido'] if r['stat_sigungu'] == r['stat_sido'] else f"{r['stat_sido']} {r['stat_sigungu']}", "design_zone": r["design_zone"],
                 "year": r["year"], "apartment_buildings": r["buildings"], "floor_area_m2": r["floor_area_m2"],
                 "electricity_toe": r["electricity_toe"], "citygas_toe": r["citygas_toe"], "district_heat_toe": dh, "total_toe": total,
                 "district_heat_share_pct": share,
                 "value_kinds": "건물에너지사용량통계(국가승인통계 제408003호) 2025 아파트, TOE 그대로(화면의 '-'는 빈칸). 비중 = 지역난방 ÷ 전체 TOE(계산). 난방 방식을 가르지 않는 시군구 합계"})
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(kept)
print("rows", len(kept), "with district heat", sum(1 for k in kept if k["district_heat_share_pct"]), "skipped", skipped)
