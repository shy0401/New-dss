"""Draft region priority for the national collection (study-region unit = national_complexes.region_code).

Inputs: regions.txt (region_code|complexes|prepared status or ''), the repo reference CSVs (climate guide: design zone and
cooling-degree-day ratio vs 전주 per 시군구; 2025 apartment energy stats: district-heat share per 시군구).
Tiers: 1 unfinished (PARTIAL/PREPARING), 2 hot or 제주 (cdd ratio >= 1.0 or zone 제주), 3 district heat share >= 30%,
4 rest. Inside a tier: more K-apt complexes first.
"""
import csv, sys, collections

regions_txt, guide_csv, stats_csv, out_csv = sys.argv[1:5]

def read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))

guide = read(guide_csv)
stats = [r for r in read(stats_csv)]

def region_of(code):
    # study regions: 시 with 구 share the 4-digit prefix + '0' (41111 -> 41110); 광역시 구 and 시 without 구 are themselves
    return code

zone = collections.defaultdict(set); cdd = collections.defaultdict(list); name = {}
for r in guide:
    zone[r["sigungu_code"]].add(r["design_zone"])
    try: cdd[r["sigungu_code"]].append(float(r["cdd_ratio_vs_jeonju"]))
    except ValueError: pass
    name[r["sigungu_code"]] = r["sigungu_name"]
heat = {}
for r in stats:
    try: heat[r["sigungu_code"]] = (float(r["district_heat_share_pct"]), float(r["floor_area_m2"] or 0))
    except ValueError: pass

rows = []
for line in open(regions_txt, encoding="utf-8"):
    p = line.rstrip("\n").split("|")
    if len(p) < 3: continue
    code, n, status = p[0], int(p[1]), p[2]
    if status == "READY": continue
    subs = [c for c in name if c == code or (code.endswith("0") and c[:4] == code[:4] and c != code and c[4] != "0")] or [code]
    subs = [c for c in subs if c in name] or [code]
    zs = sorted(set().union(*[zone[c] for c in subs if c in zone])) if any(c in zone for c in subs) else []
    cd = max([v for c in subs for v in cdd.get(c, [])], default=None)
    hs = [heat[c] for c in subs if c in heat]
    share = (sum(s * a for s, a in hs) / sum(a for s, a in hs)) if hs and sum(a for s, a in hs) else None
    nm = name.get(code) or (name.get(subs[0], "").rsplit(" ", 1)[0] if subs else "")
    if status in ("PARTIAL", "PREPARING"): tier, why = 1, "수집 중 · 덜 끝남"
    elif (cd is not None and cd >= 1.0) or "제주" in zs: tier, why = 2, "더운 지역(냉방도일 전주 이상) · 제주"
    elif share is not None and share >= 30: tier, why = 3, "공동주택 지역난방 비중 30% 이상"
    else: tier, why = 4, "나머지"
    rows.append(dict(tier=tier, region_code=code, name=nm, complexes=n, design_zone="/".join(zs), cdd_ratio_vs_jeonju_max=cd,
                     district_heat_share_pct=None if share is None else round(share, 1), reason=why))
rows.sort(key=lambda r: (r["tier"], -r["complexes"], r["region_code"]))
for i, r in enumerate(rows, 1): r["rank"] = i
with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["rank", "tier", "region_code", "name", "complexes", "design_zone", "cdd_ratio_vs_jeonju_max", "district_heat_share_pct", "reason"])
    w.writeheader(); w.writerows(rows)
c = collections.Counter(r["tier"] for r in rows); s = collections.Counter()
for r in rows: s[r["tier"]] += r["complexes"]
print("regions", len(rows), "by tier", dict(c), "complexes by tier", dict(s))
for r in rows[:40]: print(r["rank"], r["tier"], r["region_code"], r["name"], r["complexes"], r["design_zone"], r["cdd_ratio_vs_jeonju_max"], r["district_heat_share_pct"])
