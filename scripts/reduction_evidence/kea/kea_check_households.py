"""Read-only: for v2 matches in the energy table, compare certified households with K-apt households."""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text

from app.db import Session

raw_dir, run_dir = Path(sys.argv[1]), Path(sys.argv[2])
items = {}
for f in sorted((raw_dir / "pages").glob("page-*.json")):
    got = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    for it in got if isinstance(got, list) else [got]:
        items[it["RQID"]] = it
with Session() as db:
    hh = dict(db.execute(text("select kapt_code, households from apartment_complexes")).all())
bands, by_step = Counter(), {}
for row in csv.DictReader((run_dir / "matches.csv").open(encoding="utf-8")):
    if row["in_energy_table"] != "True":
        continue
    cert = items[row["RQID"]].get("HSHLD_NUMB")
    kapt = hh.get(row["kapt_code"])
    if cert in (None, "NULL", "0") or not kapt:
        band = "비교 불가(세대수 없음)"
    else:
        d = abs(int(float(cert)) - kapt) / kapt
        band = "차이 10% 이하" if d <= 0.10 else ("10~50%" if d <= 0.5 else "50% 넘음")
    bands[band] += 1
    by_step.setdefault(row["step"], Counter())[band] += 1
print(json.dumps({"all": dict(bands), "by_step": {k: dict(v) for k, v in by_step.items()}}, ensure_ascii=False))
