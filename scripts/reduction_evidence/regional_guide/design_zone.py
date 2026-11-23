"""B3: sigungu -> design-standard zone (중부1 / 중부2 / 남부 / 제주).

Source text: 건축물의 에너지절약설계기준 (국토교통부고시 제2026-360호, 시행 2026-07-08) 별표 1 비고 1)~3),
read 2026-11-20 in the law.go.kr document viewer (no file downloaded). Rule = the 비고 text, verbatim:
  중부1: 강원(고성·속초·양양·강릉·동해·삼척 제외), 경기(연천·포천·가평·남양주·의정부·양주·동두천·파주), 충북(제천), 경북(봉화·청송)
  중부2: 서울, 대전, 세종, 인천, 강원(위 6곳), 경기(위 8곳 제외), 충북(제천 제외), 충남,
         경북(봉화·청송·울진·영덕·포항·경주·청도·경산 제외), 전북, 경남(거창·함양), 대구(군위)
  남부 : 부산, 대구(군위 제외), 울산, 광주, 전남, 경북(울진·영덕·포항·경주·청도·경산), 경남(거창·함양 제외)
  제주 : 표의 넷째 열 "제주도" (비고에 따로 적지 않음)
DB sido 12 = 전남광주통합특별시 (= 광주광역시 + 전라남도, both 남부 in the 비고).

Reads admin_units (level SIGUNGU) read-only. Writes design_zone_sigungu.csv + design_zone_summary.json here.
Run: python design_zone.py
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
SOURCE = "국토교통부고시 제2026-360호 별표 1 비고(2026-07-08 시행), 2026-11-20 열람"

# sido name -> (default zone, {시·군 name without 시/군: zone})
RULES: dict[str, tuple[str, dict[str, str]]] = {
    "서울특별시": ("중부2", {}),
    "대전광역시": ("중부2", {}),
    "세종특별자치시": ("중부2", {}),
    "인천광역시": ("중부2", {}),
    "강원특별자치도": ("중부1", {n: "중부2" for n in ["고성", "속초", "양양", "강릉", "동해", "삼척"]}),
    "경기도": ("중부2", {n: "중부1" for n in ["연천", "포천", "가평", "남양주", "의정부", "양주", "동두천", "파주"]}),
    "충청북도": ("중부2", {"제천": "중부1"}),
    "충청남도": ("중부2", {}),
    "경상북도": ("중부2", {**{n: "중부1" for n in ["봉화", "청송"]},
                       **{n: "남부" for n in ["울진", "영덕", "포항", "경주", "청도", "경산"]}}),
    "전북특별자치도": ("중부2", {}),
    "경상남도": ("남부", {"거창": "중부2", "함양": "중부2"}),
    "대구광역시": ("남부", {"군위": "중부2"}),
    "부산광역시": ("남부", {}),
    "울산광역시": ("남부", {}),
    "전남광주통합특별시": ("남부", {}),
    "광주광역시": ("남부", {}),
    "전라남도": ("남부", {}),
    "제주특별자치도": ("제주", {}),
}


def read_sigungu() -> list[tuple[str, str]]:
    cmd = ["docker", "exec", "-e", "PGOPTIONS=-cdefault_transaction_read_only=on", "carbon-urban-dss-postgres-1",
           "psql", "-U", "carbon", "-d", "carbon", "-At", "-F", "|", "-c",
           "select sigungu_code, name from admin_units where level='SIGUNGU' order by sigungu_code"]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8")
    return [tuple(line.split("|", 1)) for line in out.splitlines() if line.strip()]  # type: ignore[misc]


def classify(name: str) -> tuple[str, str, str, str]:
    """(sido, city, zone, rule) — city = second token without its 시/군 ending; exact match only."""
    parts = name.split()
    sido = parts[0]
    default, exceptions = RULES[sido]  # KeyError = a sido the 비고 does not name -> stop, do not guess
    city_token = parts[1] if len(parts) > 1 else ""
    city = city_token[:-1] if city_token.endswith(("시", "군")) else ""
    if city in exceptions:
        return sido, city_token, exceptions[city], "비고에 이름이 적힌 시 · 군"
    return sido, city_token, default, "시도 기본"


def main() -> None:
    rows = read_sigungu()
    out, used = [], Counter()
    for code, name in rows:
        sido, city, zone, rule = classify(name)
        if rule.startswith("비고"):
            used[(sido, city[:-1])] += 1
        out.append({"sigungu_code": code, "sigungu_name": name, "sido_name": sido, "design_zone": zone,
                    "rule": rule, "source": SOURCE})
    with (data("regional_guide") / "design_zone_sigungu.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    named = {(s, n) for s, (_, ex) in RULES.items() for n in ex}
    summary = {
        "rows": len(out),
        "by_zone": dict(Counter(r["design_zone"] for r in out)),
        "by_sido_zone": {f"{s}|{z}": c for (s, z), c in sorted(Counter((r["sido_name"], r["design_zone"]) for r in out).items())},
        "named_exceptions": len(named),
        "named_exceptions_matched": sorted(f"{s} {n}" for (s, n) in used),
        "named_exceptions_not_found": sorted(f"{s} {n}" for (s, n) in named - set(used)),
    }
    (data("regional_guide") / "design_zone_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
