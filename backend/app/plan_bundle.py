"""One plan → one answer: ``POST /api/plans/evaluate`` (user readiness U3 step S1, 2026-11-23).

A planner enters a plan once (an area, per-use new / demolished floor area, optional floors · buildings · footprint and a
site for the legal-limit check) and gets six blocks that existing engines already compute:
  ① baseline        area.analyze → effort (observed / estimated / provided baseline)
  ② plan_emission   the U4 ``plan_added`` target: (new − demolished load) × factor — the one field everyone reads
  ③ change_model    the team change model (SCENARIO, band); asked only when requested (13–29 s), else NOT_REQUESTED
  ④ reduction       the U4 targets, measure links, recommended plan, user mix
  ⑤ district_heat   ESTIMATED district heat of the one cell (DATA_STANDARD 5.16 rule: the site cell's K-apt complexes)
  ⑥ ordinance       region rules; with a site the limits and the plan check
This module holds no emission formula: every number is read from those results. Nothing is saved. A block that is not
OK carries null numbers (never 0) and a reason. Design: project/working/methods/u3-plan-bundle-design-2026-11-23.md.
"""
from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .area import AnalyzeInput
from .db import Session
from .team_model import MAX_AREA_CELLS, Item

router = APIRouter(prefix="/api/plans", tags=["plans"])
BLOCKS = ("baseline", "plan_emission", "change_model", "reduction", "district_heat", "ordinance")
DEFAULT_BLOCKS = ("baseline", "plan_emission", "reduction", "district_heat", "ordinance")
SMALL_CHANGE_T = 1000.0   # DATA_STANDARD 5.8: below 1,000 tCO2e the change model is read for direction only (same as the screen)
AREA_TOLERANCE = 0.01   # relative: a plan typed from rounded numbers differs a little (U3 review)
# sentences and fields that only exist for a whole-area target; dropped when no target % is given (the engine ran with 0 %)
TARGET_FACTS = ("effort_target", "effort_met", "effort_new", "effort_all", "effort_offset", "effort_pv", "effort_rec", "effort_split", "effort_mix")


class SiteIn(BaseModel):
    """The site of the placement / legal-limit step (a square site around a point, like the one-cell simulation)."""
    grid_id: str | None = Field(default=None, max_length=40)
    lon: float | None = Field(default=None, ge=124, le=132)
    lat: float | None = Field(default=None, ge=33, le=39)
    rotation_deg: float = Field(default=0, ge=0, lt=90)
    site_area_m2: float = Field(gt=0, le=250_000)


class BundleIn(AnalyzeInput):
    uses_new: list[Item] = Field(default_factory=list, max_length=4)
    uses_removed: list[Item] = Field(default_factory=list, max_length=4)
    years_after: int | None = Field(default=None, ge=1, le=10)
    site: SiteIn | None = None
    include: list[Literal["baseline", "plan_emission", "change_model", "reduction", "district_heat", "ordinance"]] | None = None


def _blank(status: str, reason: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, **extra}


def normalize_plan(body: BundleIn) -> dict[str, Any]:
    """The engine plan from the per-use lines (their sums are the floor area). Two different floor areas in one plan → 422."""
    plan = body.plan.model_dump() if body.plan else {}

    def differs(a: float, b: float) -> bool:
        return abs(a - b) > max(0.5, AREA_TOLERANCE * max(abs(a), abs(b)))
    for key, lines in (("added_floor_area_m2", body.uses_new), ("removed_floor_area_m2", body.uses_removed)):
        if not lines:
            continue   # only the side that has use lines is taken from them (U3 review)
        total = sum(i.floor_area_m2 for i in lines)
        if plan.get(key) is not None and differs(float(plan[key]), total):
            raise ValueError(f"계획의 {'신축' if key.startswith('added') else '철거'} 연면적({float(plan[key]):,.0f} m²)과 용도 줄의 합({total:,.0f} m²)이 다릅니다")
        plan[key] = total
    if plan.get("floors") and plan.get("building_count") and plan.get("footprint_per_building"):
        product = float(plan["floors"]) * float(plan["building_count"]) * float(plan["footprint_per_building"])
        if plan.get("added_floor_area_m2") is None:
            plan["added_floor_area_m2"] = product   # the engine derives the same; the ratio check needs it here too
        elif differs(product, float(plan["added_floor_area_m2"])):
            raise ValueError(f"층수 × 동수 × 동당 건축면적({product:,.0f} m²)과 신축 연면적({float(plan['added_floor_area_m2']):,.0f} m²)이 다릅니다. 하나로 맞춰 주세요")
    # the use lines go on to the intensity-based load: each line with its use's observed intensity (2026-11-23, 5.9)
    for key, lines in (("uses_new", body.uses_new), ("uses_removed", body.uses_removed)):
        if lines:
            plan[key] = [{"use": i.use, "floor_area_m2": float(i.floor_area_m2)} for i in lines]
    # 2026-11-25(계획 v3 E): 주거 줄의 세대 수 합 — 태양광 인증 · 사례 수준(세대당 kW)에 씀. 세대 수가 없으면 키 없음
    dwellings = [i.dwellings for i in body.uses_new if i.use == "residential" and i.dwellings]
    if dwellings and round(sum(dwellings)) > 0:
        plan["households"] = int(round(sum(dwellings)))
    return plan


def _effort_text(facts: list[dict[str, Any]], fid: str) -> str | None:
    return next((f["text"] for f in facts if f.get("id") == fid), None)


def baseline_block(effort: dict[str, Any] | None) -> dict[str, Any]:
    if not effort or not effort.get("available"):
        return _blank("NO_BASIS", (effort or {}).get("reason") or "기준 부하를 정할 관측이 없습니다", data_class=None)
    keys = ("baseline_year", "basis", "basis_label", "fallback_from", "baseline_kwh", "baseline_kgco2eq", "intensity_kwh_per_m2",
            "intensity_area_m2", "factor_kgco2eq_per_kwh")
    return {"status": "OK", "reason": None, "data_class": effort.get("baseline_mode"), "scope": "electricity",
            "scope_label": effort.get("scope"), **{k: effort.get(k) for k in keys}}


def plan_emission_block(effort: dict[str, Any] | None, facts: list[dict[str, Any]]) -> dict[str, Any]:
    if not effort or not effort.get("available") or not effort.get("targets"):
        return _blank("NO_BASIS", (effort or {}).get("reason"), data_class="SCENARIO", net_added_kgco2eq=None)
    if not effort.get("added_floor_area_m2") and not effort.get("removed_floor_area_m2"):
        return _blank("NO_PLAN", "신축 · 철거 연면적이 없어 계획 배출을 내지 않았습니다", data_class="SCENARIO", net_added_kgco2eq=None, new_load_kwh=None)
    added = next(t for t in effort["targets"] if t["key"] == "plan_added")
    status = "OK" if added["net_added_kgco2eq"] > 0 else "NO_INCREASE"
    return {"status": status, "reason": None, "data_class": "SCENARIO", "scope": "electricity", "scope_label": effort.get("scope"),
            "new_load_kwh": effort.get("new_load_kwh"), "removed_load_kwh": effort.get("removed_load_kwh"),
            "net_added_kwh": added["net_added_kwh"], "net_added_kgco2eq": added["net_added_kgco2eq"], "bau_kgco2eq": effort.get("bau_kgco2eq"),
            "baseline_year": effort.get("baseline_year"),
            "intensity_note": f"한 원단위({effort.get('basis_label')} {effort.get('intensity_kwh_per_m2'):,.2f} kWh/m²·년)를 모든 용도의 계획 연면적에 적용했습니다. 용도별 원단위는 쓰지 않았습니다",
            "text": _effort_text(facts, "effort_added") or _effort_text(facts, "effort_added_none")}


def reduction_block(effort: dict[str, Any] | None) -> dict[str, Any]:
    if not effort or not effort.get("available"):
        return _blank("NO_BASIS", (effort or {}).get("reason"), data_class="SCENARIO")
    keys = ("target_pct", "targets", "measure_links", "measure_links_note", "recommended", "mix", "pv_yield", "region_context", "measure_estimates", "combinations", "combinations_reason")
    return {"status": "OK", "reason": None, "data_class": "SCENARIO", "scope": "electricity", **{k: effort.get(k) for k in keys}}


def change_model_block(body: BundleIn, grid_ids: list[str], region: str | None, request: Request,
                       fallback_text: str | None) -> dict[str, Any]:
    """Checks before asking the service, then the service (SCENARIO). Not OK → null numbers, the reason, and the
    intensity-based increase (②) as the fallback the screen shows instead."""
    from . import team_model
    from .team_grid import is_public, region_datasets
    fallback = {"block": "plan_emission", "text": fallback_text} if fallback_text else None

    def no(status: str, reason: str) -> dict[str, Any]:
        return _blank(status, reason, data_class="SCENARIO", change_tco2e=None, fallback=fallback)
    if is_public(request):
        return no("RESTRICTED", team_model.RESTRICTED)
    if not body.uses_new and not body.uses_removed:
        return no("NO_USES", "용도별 신축 · 철거 연면적이 없어 변화 모델을 돌리지 않았습니다(용도를 짐작해 채우지 않음)")
    if not grid_ids:
        return no("NO_CELLS", "구역에 500m 칸이 없습니다")
    if len(grid_ids) > MAX_AREA_CELLS:
        return no("TOO_MANY_CELLS", f"구역이 500m 칸 {len(grid_ids)}개로 변화 모델 한도({MAX_AREA_CELLS}칸)를 넘습니다")
    with Session() as db:   # a short session for the checks; none is held while the service computes (13~29 s)
        if not region_datasets(db, region):
            return no("NO_TEAM_TABLE_REGION", "이 지역은 팀 데이터셋(칸 상태 표)이 없어 변화 모델 예측을 아직 내지 못합니다(준비 중)")
        cells = [team_model._xy(g) for g in grid_ids if g.startswith("cell_")]
        if not any(team_model.cell_dataset(db, region, x, y) for x, y in cells):
            return no("NO_TEAM_TABLE_CELLS", "같은 시의 다른 구 표만 있고, 이 구역의 칸은 팀 데이터셋 밖입니다")
    st = team_model.service_status()
    if st.get("status") == "off":
        return no("OFF", team_model.OFF)
    if st.get("status") in ("starting", "training"):
        return no("TRAINING", "변화 모델을 학습하는 중입니다(1~3분). 잠시 뒤 다시 시도해 주세요")
    if st.get("status") in ("unavailable", "error"):
        return no("UNAVAILABLE", st.get("reason") or st.get("error") or "변화 모델 서비스가 준비되지 않았습니다")
    t0 = time.perf_counter()
    try:
        answer = team_model.predict_area(team_model.AreaPredictIn(region=region, grids=grid_ids, new=body.uses_new, removed=body.uses_removed,
                                                                  years_after=body.years_after), request)
    except HTTPException as exc:
        kind = {404: "NO_USABLE_CELL", 503: "OFF", 504: "SLOW"}.get(exc.status_code, "ERROR")
        return no(kind, str(exc.detail))
    except Exception as exc:  # noqa: BLE001 - the other blocks must still answer
        return no("ERROR", f"변화 모델 호출 중 오류({type(exc).__name__})")
    combined = answer.get("combined") or ((answer.get("results") or [None])[0]) or {}
    change = combined.get("change_tco2e")
    if change is None:
        return no("ERROR", "변화 모델이 변화량 없이 답했습니다")
    band = combined.get("band") or {}
    area = answer.get("area") or {}
    results = answer.get("results") or []
    used = len(area.get("cells_used") or results)
    want = "교차검증 1칸 개발" if used <= 1 else "교차검증 2~9칸 개발" if used < 10 else "교차검증 10칸 이상 개발"
    accuracy = next((r for r in team_model.ACCURACY["development"]["rows"] if r["band"] == want), None)
    return {"status": "OK", "reason": None, "data_class": "SCENARIO", "scope": "carbonmap_buildings",
            "scope_label": "탄소공간지도 건물 배출(전기 · 가스 · 지역난방)의 변화, tCO₂e/년",
            "reading": "direction" if change is not None and abs(change) < SMALL_CHANGE_T else "value",
            "small_change_threshold_tco2e": SMALL_CHANGE_T, "change_tco2e": change,
            **{f"band_{q}_tco2e": band.get(q) for q in ("q10", "q25", "q75", "q90")},
            "sources_tco2e": combined.get("sources_tco2e"), "state_year": area.get("year"), "years_after": body.years_after,
            # the year the service predicted for (its default when years_after is not given; U3 S2 report sentence)
            "after_year": next((r.get("after_year") for r in results if r.get("after_year") is not None), None),
            "emission_before_tco2e": round(sum(r.get("emission_before_tco2e") or 0 for r in results), 1) if results and all(r.get("emission_before_tco2e") is not None for r in results) else None,
            "cells_total": area.get("cells_total"), "cells_used": used, "cells_skipped": len(area.get("cells_skipped") or []),
            "cells": area.get("cells_used"), "model": {"train": answer.get("train"), "snapshot": answer.get("snapshot"), "dataset": answer.get("dataset"),
                                                       "name": team_model.ACCURACY["model"]},
            "inputs_kind": "TEAM_TABLE", "accuracy_row": accuracy, "requirement_text": team_model.ACCURACY["development"]["requirement"],
            "small_text": team_model.ACCURACY["development"]["small"],
            "filled": sorted({f for r in results for f in (r.get("filled") or [])}), "warnings": sorted({w for r in results for w in (r.get("warnings") or [])}),
            "out_of_range": sorted({w for r in results for w in (r.get("out_of_range") or [])}),
            "not_used": ["floors", "building_count", "footprint_per_building"], "note": answer.get("note"), "fallback": None,
            "seconds": round(time.perf_counter() - t0, 1)}


def district_heat_block(db: Any, effort: dict[str, Any] | None, cell: str | None, region: str | None) -> dict[str, Any]:
    """ESTIMATED district heat of the plan (DATA_STANDARD 5.16: the K-apt complexes of the site cell). Needs one cell."""
    from sqlalchemy import select

    from .kapt import ApartmentComplex
    from .regions import scope
    from .service import district_heat_estimate, district_heat_text, heating_share
    if not cell:
        return _blank("NEEDS_CELL", "지역난방 열은 대상지 칸 하나의 단지로 계산합니다(기준 문서 5.16). 구역이 칸 하나이거나 대지 칸(grid_id)을 정하면 계산합니다",
                      data_class="ESTIMATED", heat_kwh=None)
    if not effort or not effort.get("available"):
        return _blank("NO_BASIS", (effort or {}).get("reason"), data_class="ESTIMATED", heat_kwh=None)
    if not effort.get("added_floor_area_m2"):
        return _blank("NO_NEW_FLOOR_AREA", "신축 연면적이 없어 지역난방 열을 계산하지 않았습니다", data_class="ESTIMATED", heat_kwh=None)
    share = heating_share(db.scalars(select(ApartmentComplex).where(ApartmentComplex.grid_id == cell)).all())
    if share is None:
        return _blank("UNKNOWN_HEATING", "대상지 칸에 난방 방식을 아는 단지가 없습니다", data_class="ESTIMATED", heat_kwh=None)
    if not share.get("district_share_pct"):
        return _blank("NO_DISTRICT_HEATING", "대상지 칸 단지에 지역난방이 없습니다", data_class="ESTIMATED", heat_kwh=None,
                      complexes=share.get("complexes"), unknown_complexes=share.get("unknown_complexes"))
    year = effort.get("baseline_year")
    est = district_heat_estimate(db, year, scope(db, region), region, share, effort.get("added_floor_area_m2"))
    if not est:
        return _blank("NO_FACTOR_OR_INTENSITY", "그해 지역난방 공급자 계수나 열 원단위를 정할 수 없습니다(기준 문서 5.16)", data_class="ESTIMATED",
                      heat_kwh=None, district_share_pct=share["district_share_pct"])
    return {"status": "OK", "reason": None, "data_class": "ESTIMATED", "scope": "district_heat", "cell": cell,
            "heat_kwh": est["heat_kwh"], "heat_kgco2eq": est["carbon_kg"], "heat_kwh_per_m2": est["heat_kwh_per_m2"],
            "district_share_pct": est["district_share_pct"], "floor_area_m2": est["floor_area_m2"], "year": est["year"],
            "factor_kgco2eq_per_kwh": est["factor_kg_per_kwh"], "factor_kind": est.get("factor_kind"), "branch": est.get("branch"),
            "supplier": est.get("supplier"), "source": est.get("source"), "complexes": share.get("complexes"),
            "unknown_complexes": share.get("unknown_complexes"), "text": district_heat_text(est)}


def ordinance_block(db: Any, body: BundleIn, plan: dict[str, Any], region: str | None) -> dict[str, Any]:
    from .zoning_limits import check_plan, grid_center_lonlat, region_rules, site_zoning
    rules = region_rules(db, region)
    out: dict[str, Any] = {"rules": rules}
    site = body.site
    if site is None:
        return {"status": "NEEDS_SITE", "reason": "대지(중심 · 면적)를 정하면 용도지역 · 상한과 계획 판정을 냅니다", **out,
                "bcr_limit_pct": None, "far_limit_pct": None, "plan_bcr_pct": None, "plan_far_pct": None, "check": None}
    lonlat = (site.lon, site.lat) if site.lon is not None and site.lat is not None else grid_center_lonlat(db, site.grid_id) if site.grid_id else None
    if not lonlat:
        return {"status": "NEEDS_SITE", "reason": "대지 중심 좌표(또는 칸)를 찾지 못했습니다", **out,
                "bcr_limit_pct": None, "far_limit_pct": None, "plan_bcr_pct": None, "plan_far_pct": None, "check": None}
    zoning = site_zoning(db, lonlat[0], lonlat[1], site.site_area_m2, site.rotation_deg, housing=bool(any(i.use == "residential" for i in body.uses_new)) or not body.uses_new,
                         region_code=region)
    footprint = (float(plan["building_count"]) * float(plan["footprint_per_building"])) if plan.get("building_count") and plan.get("footprint_per_building") else None
    added = plan.get("added_floor_area_m2")
    from .domain import coverage_ratio_pct
    bcr = coverage_ratio_pct(footprint, site.site_area_m2)
    far = coverage_ratio_pct(added, site.site_area_m2)
    households = int(sum(i.dwellings or 0 for i in body.uses_new if i.use == "residential")) or None
    zoning["check"] = check_plan(zoning, bcr=bcr, far=far, site_area_m2=site.site_area_m2, households=households)
    status = "OK" if zoning.get("status") in (None, "OK", "READY") else str(zoning.get("status"))
    reason = zoning.get("reason") or {"NO_ZONING": "대지에 용도지역 자료가 없습니다", "LIMIT_UNKNOWN": "대지의 일부 용도지역 상한을 모릅니다",
                                      "NOT_COLLECTED": "이 지역 용도지역을 아직 받지 않았습니다"}.get(status)
    return {"status": status, "reason": reason, **out, "site": zoning, "bcr_limit_pct": zoning.get("bcr_limit"), "far_limit_pct": zoning.get("far_limit"),
            "plan_bcr_pct": bcr, "plan_far_pct": far, "check": zoning["check"],
            "note": "구역 전체 신축 연면적을 이 대지 한 곳에 짓는 것으로 보고 비율을 냈습니다. 공동주택 상한은 주거 용도 줄이 있을 때(용도 줄이 없으면 공동주택으로 봄) 적용합니다"}


def strip_target(analysis: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """No target % given: the engine ran with 0 % only for the plan's own increase. Everything that reads a whole-area
    target (sentences, the area target, the recommended plan, the user mix, the effort curve) is removed (U3 review)."""
    effort = analysis.get("effort")
    if effort:
        effort = dict(effort, target_pct=None, target_kgco2eq=None, required_reduction_kgco2eq=None, already_met=None, options=None, curve=None,
                      recommended=None, mix=None, feasible_with_new_only=None,
                      targets=[t for t in effort.get("targets") or [] if t["key"] == "plan_added"],
                      measure_links=[m for m in effort.get("measure_links") or [] if m["target"] == "plan_added"])
    facts = [f for f in analysis.get("facts") or [] if not any(f.get("id", "").startswith(p) for p in TARGET_FACTS)]
    history = dict(analysis.get("history") or {})
    history.pop("industry", None)
    return dict(analysis, effort=effort, facts=facts, history=history), effort, facts


SCOPES = [
    {"key": "plan_emission", "label": "원단위 기반 계획 배출(이 화면 계산)", "data_class": "SCENARIO", "scope": "전력 운영탄소만(가스 · 열 제외)",
     "what": "관측 원단위 × 계획 연면적 × 전력 계수"},
    {"key": "district_heat", "label": "지역난방 열(추정)", "data_class": "ESTIMATED", "scope": "지역난방 열만", "what": "계획 연면적 × 지역난방 비중 × 열 원단위 × 공급자 계수"},
    {"key": "change_model", "label": "팀 변화 모델 예측", "data_class": "SCENARIO", "scope": "탄소공간지도 건물 배출(전기 · 가스 · 지역난방)",
     "what": "과거 개발 사례로 학습한 모델의 변화 예측(구간 함께)"},
    {"key": "simulation", "label": "한 칸 계획안(시뮬레이션 화면)", "data_class": "SCENARIO", "scope": "전력 + 가스", "what": "그 화면의 계획안 계산(여기서는 계산하지 않음)"},
]


@router.post("/evaluate")
def evaluate(body: BundleIn, request: Request) -> dict[str, Any]:
    """계획 하나를 한 번 넣으면 기준 배출 · 원단위 기반 계획 배출 · (요청하면) 변화 모델 · 감축 · 지역난방 열 · 조례를 블록으로 돌려준다.
    저장하지 않는다. 숫자는 모두 기존 계산 결과에서 꺼낸다(새 산식 없음)."""
    from .area import analyze
    from .regions import RegionNotReady
    from .team_grid import is_public
    wanted = set(body.include or DEFAULT_BLOCKS)
    try:
        plan = normalize_plan(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    timing: dict[str, float] = {}
    with Session() as db:
        t0 = time.perf_counter()
        try:
            analysis = analyze(db, body.area.model_dump(), body.from_year, body.to_year, body.event_year, body.window, plan or None,
                               body.target_pct if body.target_pct is not None else 0.0, body.pv_yield_kwh_per_kw, region=body.region,
                               effort_basis=body.effort_basis, measures=body.measures.model_dump() if body.measures else None, public=is_public(request))
        except RegionNotReady as exc:
            raise HTTPException(404, str(exc)) from None
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from None
        timing["analyze"] = round(time.perf_counter() - t0, 2)
        effort = analysis.get("effort")
        facts = analysis.get("facts") or []
        area = (analysis.get("history") or {}).get("area") or {}
        grid_ids = list(area.get("grid_ids") or [])
        region = (analysis.get("region") or {}).get("code") or body.region
        cell = (body.site.grid_id if body.site and body.site.grid_id in grid_ids else None) or (grid_ids[0] if len(grid_ids) == 1 else None)
        if body.target_pct is None:
            analysis, effort, facts = strip_target(analysis)
        blocks: dict[str, Any] = {}
        blocks["baseline"] = baseline_block(effort) if "baseline" in wanted else _blank("NOT_REQUESTED")
        blocks["plan_emission"] = plan_emission_block(effort, facts) if "plan_emission" in wanted else _blank("NOT_REQUESTED")
        blocks["reduction"] = reduction_block(effort) if "reduction" in wanted else _blank("NOT_REQUESTED")
        if body.target_pct is None and blocks["reduction"].get("status") == "OK":
            blocks["reduction"]["note"] = "목표 %를 넣지 않아 '구역 전체 목표' 기준은 내지 않았습니다"
        if "district_heat" in wanted:
            t0 = time.perf_counter()
            blocks["district_heat"] = district_heat_block(db, effort, cell, region)
            timing["district_heat"] = round(time.perf_counter() - t0, 2)
        else:
            blocks["district_heat"] = _blank("NOT_REQUESTED")
        if "ordinance" in wanted:
            t0 = time.perf_counter()
            blocks["ordinance"] = ordinance_block(db, body, plan, region)
            timing["ordinance"] = round(time.perf_counter() - t0, 2)
        else:
            blocks["ordinance"] = _blank("NOT_REQUESTED")

    if "change_model" in wanted:
        t0 = time.perf_counter()
        blocks["change_model"] = change_model_block(body, grid_ids, region, request, (blocks["plan_emission"] or {}).get("text"))
        timing["change_model"] = round(time.perf_counter() - t0, 2)
    else:
        blocks["change_model"] = _blank("NOT_REQUESTED")
    footprint = (effort or {}).get("plan_roof_m2")
    return {"plan": {"added_floor_area_m2": plan.get("added_floor_area_m2"), "removed_floor_area_m2": plan.get("removed_floor_area_m2"),
                     "uses_new": [i.model_dump() for i in body.uses_new], "uses_removed": [i.model_dump() for i in body.uses_removed],
                     "floors": plan.get("floors"), "building_count": plan.get("building_count"), "footprint_per_building": plan.get("footprint_per_building"),
                     "footprint_sum_m2": footprint, "footprint_basis": (effort or {}).get("plan_roof_basis"), "grid_ids": grid_ids, "grid_count": len(grid_ids),
                     "site": body.site.model_dump() if body.site else None,
                     # 2026-11-25(계획 v3 D): 녹지 면적은 넣은 때만 되돌려 적음(안 넣으면 응답이 전과 같음)
                     **({"green_area_m2": plan["green_area_m2"]} if plan.get("green_area_m2") else {}),
                     "not_used_by": {"change_model": ["floors", "building_count", "footprint_per_building"], "intensity": ["use", "dwellings"]}},
            "analysis": analysis, "blocks": blocks, "scopes": SCOPES, "facts": facts, "timing_s": timing}
