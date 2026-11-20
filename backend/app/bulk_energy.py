"""건축HUB 대용량 건물에너지 파일(지번별 · 월별 전국 파일) → ``energy_monthly``.

The 건축HUB 대용량 데이터 제공 page publishes the same 세움터 data the API answers, one zip per month and energy type
(``MART_KEY_GAS_ENERGY_DATA_YYYYMM.zip`` / ``MART_KEY_ELCTY_ENERGY_DATA_YYYYMM.zip``, UTF-8 text, ``|``-separated, no
header). 2026-11-21: 2025-01 of 32 시군구, 234,340 지번 × 전기 · 가스 were all equal to the API (docs/records). Reading a
month of the whole country takes seconds, against hours of API pages, so a region step takes the months it finds here
and asks the API only for the rest.

Columns (0-based): 0 사용년월, 1 순번, 2 시군구코드, 3 법정동코드, 4 시도명, 5 시군구명, 6 법정동명, 7 대지구분코드, 8 본번, 9 부번,
10 새주소도로코드, 11 도로명, 12 지상지하코드, 13 지상지하명, 14 새주소본번, 15 새주소부번, 16 사용량(kWh).

* A 지번 with several road addresses comes as several lines (순번), mostly with the same 사용량: one parcel, the value
  once (the API lists the 지번 once). When the lines differ, the API answers the lowest 순번's value (2025-01 ~ 12:
  120 such 지번, all 120 equal to the lowest 순번): the same is stored, the other values are kept in
  ``raw_record.bulk_other_useQty`` and counted as ``conflicts``. They are not added up (whether they are other meters
  is 확인 필요).
* Same rules as the API rows: same source name, negative or blank → ``usage_kwh`` NULL with the raw value kept.
* 건축HUB rows already in the table (API) are never overwritten; their value is compared (``same`` / ``different``).
  An earlier K-apt row of the same parcel and month is replaced by the meter value with the old one kept, as the API
  collector does (``replaced``).
* Files are the downloaded originals under ``data/raw/bldhub_bulk_energy/<받은 날>/`` (never edited); when a month was
  received twice, the newest folder wins.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

from sqlalchemy import insert, select

from .domain import number

HUB = "국토교통부 건축HUB"
FILE_RE = re.compile(r"^MART_KEY_(GAS|ELCTY)_ENERGY_DATA_(\d{6})\.zip$")
FILE_TYPES = {"GAS": "GAS", "ELCTY": "ELECTRICITY"}
ENERGY_TYPES = ("ELECTRICITY", "GAS")
COLUMNS = 17


def bulk_root() -> Path:
    return Path(os.getenv("DATA_DIR", "data")) / "raw" / "bldhub_bulk_energy"


def month_files(root: Path | None = None) -> dict[str, dict[str, Path]]:
    """{use_ym: {energy_type: zip path}} of every received file; a later 받은 날 folder replaces an earlier one."""
    root = root or bulk_root()
    found: dict[str, dict[str, Path]] = {}
    if not root.is_dir():
        return found
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(folder.iterdir()):
            match = FILE_RE.match(path.name)
            if match:
                found.setdefault(match.group(2), {})[FILE_TYPES[match.group(1)]] = path
    return found


def complete_months(year: int, root: Path | None = None) -> list[str]:
    """Months of ``year`` that have both the electricity and the gas file."""
    files = month_files(root)
    return [ym for ym in (f"{year}{m:02d}" for m in range(1, 13)) if all(t in files.get(ym, {}) for t in ENERGY_TYPES)]


def _int_text(value: str) -> str:
    value = (value or "").strip()
    return str(int(value)) if value.isdigit() else value


def parcel_address(p: list[str]) -> str:
    """지번 주소 like the API's ``platPlc``: '경기도 남양주시 호평동 산8-5'."""
    lot = {"1": "산", "2": "블록"}.get(p[7].strip(), "")
    bun, ji = _int_text(p[8]), _int_text(p[9])
    number_part = f"{bun}-{ji}" if ji not in ("", "0") else ("" if bun in ("", "0") else bun)
    # the API keeps the space before an empty number ('경기도 수원시 영통구 이의동 ', '… 대목리 산')
    return f"{p[4].strip()} {p[5].strip()} {p[6].strip()} {lot}{number_part}"


def road_address(p: list[str]) -> str | None:
    """도로명 주소 like the API's ``newPlatPlc``: '경기도 남양주시 늘을1로 255 (호평동) '; None without a road name."""
    road = p[11].strip()
    if not road:
        return None
    main, sub = _int_text(p[14]), _int_text(p[15])
    building = f"{main}-{sub}" if sub not in ("", "0") else main
    underground = "지하" if p[12].strip() == "1" else ""  # API: '성남대로 지하491'
    return f"{p[4].strip()} {p[5].strip()} {road} {underground}{building} ({p[6].strip()}) "


def read_month(path: Path, energy_type: str, wanted: set[tuple[str, str]] | None = None) -> dict[tuple[str, ...], dict[str, Any]]:
    """{(sigungu, bjdong, lot, bun, ji, use_ym, energy_type): {value, raw, rows, conflict, record}} of one file.

    ``wanted`` = {(file 시군구 code, 법정동 code)} to keep (None = all)."""
    out: dict[tuple[str, ...], dict[str, Any]] = {}
    with zipfile.ZipFile(path) as archive:
        member = next(i for i in archive.infolist() if not i.is_dir())
        with archive.open(member) as handle:
            for line in io.TextIOWrapper(handle, encoding="utf-8-sig", newline=""):
                p = line.rstrip("\r\n").split("|")
                if len(p) < COLUMNS or not p[0].isdigit():
                    continue
                if wanted is not None and (p[2], p[3]) not in wanted:
                    continue
                lot = p[7].strip() or "0"
                key = (p[2], p[3], lot, p[8].strip().zfill(4)[-4:], p[9].strip().zfill(4)[-4:], p[0], energy_type)
                raw = p[16].strip()
                seq = int(p[1]) if p[1].isdigit() else 10**9
                road = road_address(p)
                item = out.get(key)
                if item is None:
                    record: dict[str, Any] = {"platPlc": parcel_address(p), "bulk_file": path.name}
                    if road:
                        record["newPlatPlc"] = road
                    item = out[key] = {"rows": 0, "conflict": False, "record": record, "lines": [],
                                       "seq": seq if road else 10**9, "value_seq": 10**9, "raw": None, "value": None}
                item["rows"] += 1
                item["lines"].append(raw)
                # Tried against the API (2025-01 ~ 12, 2,575,968 지번): it answers the value and the road address of the
                # lowest 순번. Lines of one 지번 with other values (2025-12: 120 지번) are kept in the record only.
                if seq < item["value_seq"]:
                    item["value_seq"], item["raw"], item["value"] = seq, raw, number(raw)
                if road and seq < item["seq"]:
                    item["record"]["newPlatPlc"], item["seq"] = road, seq
    for item in out.values():
        raw = item["raw"]
        item["record"]["useQty"] = int(raw) if re.fullmatch(r"-?\d+", raw) else raw
        others = [v for v in item.pop("lines") if v != raw]
        if others:
            item["conflict"] = True
            item["record"]["bulk_other_useQty"] = [int(v) if re.fullmatch(r"-?\d+", v) else v for v in others]
    return out


def import_months(db: Any, regions: Iterable[dict[str, str]], months: Iterable[str], *, root: Path | None = None,
                  progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Store the file rows of ``regions`` ([{sigunguCd, bjdongCd}]) for ``months`` (each needs both files)."""
    from .energy_parcels import place_missing_parcels, request_sigungu, _GRID_CACHE
    from .models import EnergyMonthly
    files = month_files(root)
    regions = list(regions)
    stats: dict[str, Any] = {"months": [], "inserted": 0, "replaced": 0, "same": 0, "different": 0, "conflicts": 0, "lines_merged": 0, "files": []}
    for ym in months:
        pair = files.get(ym, {})
        if not all(t in pair for t in ENERGY_TYPES):
            raise FileNotFoundError(f"{ym} 대용량 파일(전기 · 가스)이 다 있지 않습니다")
        # the file uses the code the provider used that month (전북 45xxx up to 2023-10, like the API)
        to_ours = {(request_sigungu(r["sigunguCd"], ym), r["bjdongCd"]): (r["sigunguCd"], r["bjdongCd"]) for r in regions}
        wanted = set(to_ours)
        for energy_type in ENERGY_TYPES:
            rows = read_month(pair[energy_type], energy_type, wanted)
            stats["files"].append(pair[energy_type].name)
            by_dong: dict[tuple[str, str], list[tuple[tuple[str, ...], dict[str, Any]]]] = {}
            for key, item in rows.items():
                by_dong.setdefault(to_ours[(key[0], key[1])], []).append((key, item))
            for (sg, bd), items in by_dong.items():
                existing = {(r.lot_type or "0", r.bun, r.ji): (r.id, r.usage_kwh, r.source) for r in db.execute(
                    select(EnergyMonthly.id, EnergyMonthly.lot_type, EnergyMonthly.bun, EnergyMonthly.ji, EnergyMonthly.usage_kwh,
                           EnergyMonthly.source).where(
                        EnergyMonthly.sigungu_code == sg, EnergyMonthly.bjdong_code == bd, EnergyMonthly.use_ym == ym,
                        EnergyMonthly.energy_type == energy_type))}
                new_rows = []
                for key, item in items:
                    lot, bun, ji = key[2], key[3], key[4]
                    if item["conflict"]:
                        stats["conflicts"] += 1      # stored with the lowest 순번 value, like the API
                    if item["rows"] > 1:
                        stats["lines_merged"] += item["rows"] - 1
                    record = dict(item["record"])
                    if item["rows"] > 1:
                        record["bulk_rows"] = item["rows"]
                    if (lot, bun, ji) in existing:
                        row_id, old_value, old_source = existing[(lot, bun, ji)]
                        if old_source == HUB:  # an API row: kept, only compared
                            stats["same" if old_value == item["value"] else "different"] += 1
                            continue
                        # an earlier K-apt value of the parcel gives way to the building meter, as in the API collector
                        row = db.get(EnergyMonthly, row_id)
                        merged = dict(row.raw_record or {}, **record)
                        if old_value is not None:
                            merged.update(replaced_source=old_source, replaced_usage_kwh=old_value)
                        row.source, row.usage_kwh, row.raw_record = HUB, item["value"], merged
                        stats["replaced"] += 1
                        continue
                    new_rows.append(dict(source=HUB, sigungu_code=sg, bjdong_code=bd, lot_type=lot, bun=bun, ji=ji, use_ym=ym,
                                         energy_type=energy_type, usage_kwh=item["value"], raw_record=record))
                if new_rows:
                    db.execute(insert(EnergyMonthly), new_rows)
                    stats["inserted"] += len(new_rows)
            db.commit()
        stats["months"].append(ym)
        if progress:
            progress(f"{ym[:4]}-{ym[4:]} 대용량 파일: 새 행 누계 {stats['inserted']:,}")
    if stats["months"]:
        stats["placed_by_main_lot"] = place_missing_parcels(db, sorted({r["sigunguCd"] for r in regions}))["placed"]
        _GRID_CACHE.clear()
    return stats
