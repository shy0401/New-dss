"""Observed electricity intensity by building use (2026-11-23, records/2026-11-23-use-intensity.md).

For every READY region and for all READY regions together: 건축HUB parcels with 12 months of electricity in ``--year``
whose main buildings (주건축물) share one 주용도, kWh ÷ cleaned register 연면적 of all buildings on the parcel
(``official.register_areas``), kept within the screen's 2~1,500 kWh/m². Per use class of the plan lines (the team model's
use names), the area-weighted intensity = Σ kWh ÷ Σ 연면적 (DATA_STANDARD 5.2). Reads the DB only.
usage (api container, backend at /app): python /scripts/build_use_intensity.py --year 2025 --out /app/reference/use_intensity_2025.csv
"""
import argparse
import csv
import sys
from collections import defaultdict

sys.path.insert(0, "/app")
from sqlalchemy import func, select, text  # noqa: E402

from app.db import Session  # noqa: E402
from app.energy_parcels import HUB, MAX_KWH_PER_M2, MIN_KWH_PER_M2, parcel_pnu  # noqa: E402
from app.models import EnergyMonthly  # noqa: E402
from app.official import BuildingRegister, register_areas  # noqa: E402
from app.regions import scope  # noqa: E402

# plan use (team model names) ← register 주용도. Uses without a row keep the area's own intensity (residential: the
# area's observed basis; officetel: registered as 업무시설 but lived in; knowledge_industry / industrial: too few parcels).
USE_CLASSES = {
    "commercial": ("제1종근린생활시설", "제2종근린생활시설", "근린생활시설"),
    "office": ("업무시설",),
    "large_retail": ("판매시설",),
    "education": ("교육연구시설",),
    "medical_welfare": ("의료시설", "노유자시설"),
}

p = argparse.ArgumentParser()
p.add_argument("--year", type=int, default=2025)
p.add_argument("--out", required=True)
args = p.parse_args()
y = args.year
use_of = {u: cls for cls, uses in USE_CLASSES.items() for u in uses}

with Session() as db:
    region_of = {}
    for (code,) in db.execute(text("select code from study_regions where status='READY' order by code")):
        for sg in scope(db, code).legal_codes or [code]:
            region_of.setdefault(sg, code)
    codes = sorted(region_of)
    rows = db.execute(select(EnergyMonthly.sigungu_code, EnergyMonthly.bjdong_code, EnergyMonthly.lot_type, EnergyMonthly.bun, EnergyMonthly.ji,
                             func.count(func.distinct(EnergyMonthly.use_ym)), func.sum(EnergyMonthly.usage_kwh))
                      .where(EnergyMonthly.use_ym.between(f"{y}01", f"{y}12"), EnergyMonthly.source == HUB, EnergyMonthly.energy_type == "ELECTRICITY",
                             EnergyMonthly.usage_kwh.is_not(None), EnergyMonthly.sigungu_code.in_(codes))
                      .group_by(EnergyMonthly.sigungu_code, EnergyMonthly.bjdong_code, EnergyMonthly.lot_type, EnergyMonthly.bun, EnergyMonthly.ji)).all()
    kwh = {parcel_pnu(sg, bd, lot, bun, ji): float(v) for sg, bd, lot, bun, ji, n, v in rows if n == 12 and v}
    gfa, uses = defaultdict(float), defaultdict(set)
    for pnu, attrs in db.execute(select(BuildingRegister.parcel_code, BuildingRegister.attributes)
                                 .where(func.substr(BuildingRegister.parcel_code, 1, 5).in_(codes))):
        if pnu not in kwh:
            continue
        a = attrs or {}
        area = register_areas(a)[0]
        if area:
            gfa[pnu] += area
        if (a.get("main_or_annex") or "주건축물") == "주건축물" and a.get("building_use"):
            uses[pnu].add(str(a["building_use"]).strip())

agg = defaultdict(lambda: [0, 0.0, 0.0])  # (region, class) → parcels, kWh, m²
for pnu, e in kwh.items():
    if len(uses.get(pnu, ())) != 1 or not gfa.get(pnu):
        continue
    cls = use_of.get(next(iter(uses[pnu])))
    if cls is None or not (MIN_KWH_PER_M2 <= e / gfa[pnu] <= MAX_KWH_PER_M2):
        continue
    for region in (region_of[pnu[:5]], "ALL"):
        a = agg[(region, cls)]
        a[0] += 1; a[1] += e; a[2] += gfa[pnu]

with open(args.out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["region_code", "use_class", "register_uses", "year", "parcels", "kwh", "area_m2", "kwh_per_m2", "source"])
    for (region, cls), (n, e, a) in sorted(agg.items()):
        w.writerow([region, cls, "+".join(USE_CLASSES[cls]), y, n, round(e), round(a), round(e / a, 2),
                    f"건축HUB 건물 에너지 {y} 전력(12개월 계측 지번) ÷ 건축물대장 표제부 연면적, 주건축물 주용도 하나, 2~1,500 kWh/m²"])
print("rows", len(agg), "| ALL:", {c: round(v[1] / v[2], 1) for (r, c), v in agg.items() if r == "ALL"})
