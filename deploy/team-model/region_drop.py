"""Region-drop exclusion judged per cell for the change model's training rows (2026-11-19, roadmap stage 5 · 7-A).

The team rule (``dataset/surge.py``, ADR 0008 addendum 2026-10-18/19) finds the (region, year, energy) whose regional
total fell to ``max_ratio`` x the median of the earlier dataset years or below and marks **every** cell that ever had the
energy. Here the same years are found with the team ``drop_years`` and ``rules.yaml`` values, on the electricity with the
2024 factor harmonized (as the target, PR #14), and a cell stays unmarked when its own value that year is present and
>= ``max_ratio`` x the median of its own earlier years (>= ``min_earlier_years`` of them). Other exclusion reasons stay.

Rows taken back this way join the training **pairs** only: their ``train_usable`` keeps the team value, so they are
not development cases (case weight x10). Taking them back as cases moved the 명지 site prediction from -4 % to +48 % of the
K-apt meters (record §29-1, §37) while this training-only form did not (§37 rule 3).
Nothing is written back; the table is re-judged in memory when the service loads it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

ISSUE = "suspect_region_drop"
_ELEC, _GAS, _HEAT, _TOTAL = "elec_tco2e_total", "gas_tco2e_total", "heat_tco2e_total", "buildings_tco2e_total"


def harmonized(table: Any, factor_high: set[str], base: float, high: float) -> Any:
    """A copy with the 2024 electricity of the ``high`` regions on the ``base`` factor (for judging only)."""
    t = table.copy()
    if factor_high and "region" in t:
        rows = (t["year"] == 2024) & t["region"].astype(str).str[:5].isin(factor_high)
        t.loc[rows, _ELEC] = t.loc[rows, _ELEC] * (base / high)
        t[_TOTAL] = t[[_ELEC, _GAS, _HEAT]].sum(axis=1, min_count=1)
    return t


def cell_usable(table: Any, rules_path: Path) -> tuple[Any, dict[str, int]]:
    """Usable rows with the region-drop marks re-judged per cell (other exclusion reasons as the team marked them)."""
    import pandas as pd
    import yaml
    from urban_carbon.core.rules import load_region_drop_rule
    from urban_carbon.dataset.surge import drop_years

    rule = load_region_drop_rule(Path(rules_path))
    exclude = set(yaml.safe_load(Path(rules_path).read_text(encoding="utf-8"))["training"]["exclude"])
    issues = table["train_issues"].fillna("").astype(str).map(lambda x: {i for i in x.split("+") if i})
    other = issues.map(lambda s: bool((s - {ISSUE}) & exclude)).to_numpy()
    marked = pd.Series(False, index=table.index)
    failed = pd.Series(False, index=table.index)
    for region, year, energy in drop_years(table, rule):
        g = table[table["region"] == region]
        ever = g.groupby("grid_id_500m")[energy].transform(lambda v: (v.fillna(0) > 0).any())
        rows = g.index[(g["year"] == year) & ever]
        marked.loc[rows] = True
        earlier = g[g["year"] < year].pivot_table(index="grid_id_500m", columns="year", values=energy, aggfunc="first")
        count = earlier.notna().sum(axis=1)
        median = earlier.median(axis=1, skipna=True)
        now = g.loc[rows].set_index("grid_id_500m")[energy]
        ok = (now.notna() & (count.reindex(now.index) >= rule.min_earlier_years)
              & (now >= rule.max_ratio * median.reindex(now.index))).to_numpy()
        failed.loc[rows[~ok]] = True
    flag = (marked & failed).to_numpy()
    use = ~other & ~flag
    return use, {"region_drop_marked_rows": int(marked.sum()), "region_drop_kept_rows": int(flag.sum()),
                 "region_drop_back_rows": int((marked.to_numpy() & ~flag & ~other).sum())}


def training_table(folder: Path, rules_path: Path, factor_high: set[str], base: float, high: float, add_energy_mix: Any) -> tuple[Any, dict[str, int]]:
    """The training table the service learns from: rows usable under the per-cell region-drop rule, original values
    (``official_inputs`` harmonizes 2024 electricity afterwards), ``train_usable`` as the team marked it."""
    import pandas as pd

    full = pd.read_csv(Path(folder) / "training.csv", encoding="utf-8", low_memory=False)
    team = full["train_usable"].astype(bool).to_numpy()
    use, note = cell_usable(harmonized(full, factor_high, base, high), rules_path)
    full["train_usable"] = use & team
    note.update({"team_usable_rows": int(team.sum()), "rows": int(use.sum())})
    return add_energy_mix(full[use].reset_index(drop=True)), note
