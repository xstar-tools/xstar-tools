"""Diagnostic-only fixed-state attribution products for all-element C++ qualification.

This module does not alter any rate, matrix, population, thermal term, DSEC
controller state, or publication product.  It serializes the already-computed
source-faithful Python fixed-state result so it can be compared directly with
native C++ diagnostics at an identical entry state.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .local_zone import FixedStateCalcHMCAllResult
else:
    FixedStateCalcHMCAllResult = Any


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _ca_element(result: FixedStateCalcHMCAllResult, element_z: int):
    for item in result.element_results:
        if int(item.request.element_z) == int(element_z):
            return item
    raise RuntimeError(f"fixed-state result has no element Z={element_z}")


def python_element_attribution_rows(
    result: FixedStateCalcHMCAllResult, *, element_z: int = 20
) -> dict[str, list[dict[str, Any]]]:
    item = _ca_element(result, element_z)
    solve = item.equilibrium.solve
    if solve is None:
        raise RuntimeError(f"element Z={element_z} has no completed population solve")
    assembly = item.equilibrium.assembly
    basis = assembly.basis
    abundance = float(item.request.abundance)

    stage_rows: list[dict[str, Any]] = []
    electron_rows: list[dict[str, Any]] = []
    for stage in range(1, int(element_z) + 2):
        if stage == int(element_z) + 1:
            fraction = float(item.fully_stripped_fraction)
            charge = int(element_z)
            active = stage == int(element_z) + 1 or (
                int(item.selected_min_ion_stage) <= stage <= int(item.selected_max_ion_stage) + 1
            )
        else:
            fraction = float(item.ion_fractions.get(stage, 0.0))
            charge = stage - 1
            active = int(item.selected_min_ion_stage) <= stage <= int(item.selected_max_ion_stage)
        contribution = fraction * float(charge) * abundance
        row = {
            "source": "python",
            "element_z": int(element_z),
            "stage": stage,
            "ion_charge": charge,
            "active_stage": int(bool(active)),
            "final_fraction": fraction,
            "abundance": abundance,
        }
        stage_rows.append(row)
        electron_rows.append({**row, "electron_contribution": contribution})

    compact_rows: list[dict[str, Any]] = []
    ion_stage_map = basis.ion_stage
    for idx, basis_row in enumerate(basis.rows):
        compact = int(basis_row.compact_index)
        compact_rows.append(
            {
                "source": "python",
                "element_z": int(element_z),
                "active_min_stage": int(item.selected_min_ion_stage),
                "active_max_stage": int(item.selected_max_ion_stage),
                "compact_row": compact,
                "superlevel": int(basis_row.superlevel),
                "ion_counter": int(basis_row.ion_counter),
                "ion_stage": int(ion_stage_map[compact]),
                "is_normalization_row": int(compact == int(basis.normalization_row)),
                # The assembly seed carries a one-based guard at index zero;
                # the solved output is a zero-based n_rows vector.
                "initial_population": float(assembly.initial_populations[compact]),
                "final_population": float(solve.populations[idx]),
                "roles_json": json.dumps(basis_row.roles, sort_keys=True, separators=(",", ":"), default=str),
            }
        )

    # v0.6.48.12.3.35 diagnostic-only source-record surface.  These rows
    # expose the already-computed source-faithful ucalc results so a captured
    # C++ fixed state can be compared record-by-record without changing any
    # rate, matrix, population, emissivity, or publication calculation.
    record_result_rows: list[dict[str, Any]] = []
    scalar_fields = (
        "record", "data_type", "rate_type", "ion_index", "ion_stage",
        "idest1", "idest2", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
        "ans1_after_calc_hmc_ion_filter", "ans2_after_calc_hmc_ion_filter",
        "density_scale", "escape_factor_in", "escape_factor_out", "status",
        "ready", "rates_backend",
    )
    for ordinal, raw in enumerate(assembly.record_results, start=1):
        row: dict[str, Any] = {"source": "python", "element_z": int(element_z), "record_order": ordinal}
        for field in scalar_fields:
            value = raw.get(field)
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                row[field] = value
        record_result_rows.append(row)

    preliminary_record_rows: list[dict[str, Any]] = []
    preliminary_record_order = 0
    for stage, rate_result in sorted(item.calc_ion_rates.items()):
        for contribution in rate_result.contributions:
            preliminary_record_order += 1
            preliminary_record_rows.append({
                "source": "python",
                "element_z": int(element_z),
                "record_order": preliminary_record_order,
                "record": int(contribution.record),
                "data_type": int(contribution.data_type),
                "rate_type": int(contribution.rate_type),
                "ion_stage": int(stage),
                "nlev": int(rate_result.nlev),
                "idest1": int(contribution.idest1),
                "idest2": int(contribution.idest2),
                "status": str(contribution.status),
                "ans1": float(contribution.ans1),
                "ans2": float(contribution.ans2),
                "ans3": float(contribution.ans3),
                "ans4": float(contribution.ans4),
                "ans5": float(contribution.ans5),
                "ans6": float(contribution.ans6),
                "ionization_contribution": float(contribution.added_to_pirti),
                "recombination_contribution": float(contribution.added_to_rrrti),
                "running_pirti": float(contribution.pirti_after),
                "running_rrrti": float(contribution.rrrti_after),
            })

    preliminary_stage_rows: list[dict[str, Any]] = []
    for stage in range(1, int(element_z) + 2):
        preliminary_stage_rows.append({
            "source": "python",
            "element_z": int(element_z),
            "stage": stage,
            "ion_charge": stage - 1,
            "preliminary_ionization": float(item.preliminary_pirt.get(stage, 0.0)),
            "preliminary_recombination": float(item.preliminary_rrrt.get(stage, 0.0)),
            "preliminary_fraction": float(item.preliminary_ion_fractions.get(stage, 0.0)),
            "second_pass_ionization": float(item.second_pass_pirt.get(stage, 0.0)),
            "second_pass_recombination": float(item.second_pass_rrrt.get(stage, 0.0)),
            "final_fraction": float(item.fully_stripped_fraction if stage == int(element_z) + 1 else item.ion_fractions.get(stage, 0.0)),
        })

    all_matrix_terms: list[dict[str, Any]] = []
    for term in assembly.terms:
        all_matrix_terms.append(
            {
                "source": "python",
                "element_z": int(element_z),
                "term_index": int(term.term_index),
                "record": int(term.record),
                "data_type": int(term.data_type),
                "rate_type": int(term.rate_type),
                "ion_index": int(term.ion_index),
                "ion_stage": int(term.ion_stage),
                "role": str(term.role),
                "row": int(term.row),
                "column": int(term.column),
                "aj1": float(term.aj1),
                "aj2": float(term.aj2),
                "cj": float(term.cj),
                "cj2": float(term.cj2),
                "idest1": int(term.idest1),
                "idest2": int(term.idest2),
                "lower_endpoint": int(term.lower_endpoint),
                "upper_endpoint": int(term.upper_endpoint),
                "source_row_unclamped": int(term.source_row_unclamped),
                "source_column_unclamped": int(term.source_column_unclamped),
                "source_ipmat_clamped": int(bool(term.source_ipmat_clamped)),
                "ucalc_status": str(term.ucalc_status),
            }
        )

    term_rows: list[dict[str, Any]] = []
    for term in assembly.terms:
        if int(term.row) != int(term.column):
            continue
        pop = float(solve.populations[int(term.row) - 1])
        heating = cooling = heating2 = cooling2 = 0.0
        if float(term.cj) > 0.0:
            cooling = pop * float(term.cj) * abundance
        else:
            heating = -pop * float(term.cj) * abundance
        if float(term.cj2) > 0.0:
            cooling2 = pop * float(term.cj2) * abundance
        else:
            heating2 = -pop * float(term.cj2) * abundance
        term_rows.append(
            {
                "source": "python",
                "element_z": int(element_z),
                "term_index": int(term.term_index),
                "record": int(term.record),
                "data_type": int(term.data_type),
                "rate_type": int(term.rate_type),
                "ion_index": int(term.ion_index),
                "ion_stage": int(term.ion_stage),
                "compact_row": int(term.row),
                "role": str(term.role),
                "abundance": abundance,
                "compact_population": pop,
                "cj": float(term.cj),
                "cj2": float(term.cj2),
                "heating_contribution": heating,
                "cooling_contribution": cooling,
                "heating2_contribution": heating2,
                "cooling2_contribution": cooling2,
                "absolute_thermal_contribution": heating + cooling + heating2 + cooling2,
            }
        )

    record_groups: dict[tuple[int, int, int, int, int], dict[str, Any]] = {}
    type_groups: dict[tuple[int, int], dict[str, Any]] = {}
    channels = (
        "heating_contribution", "cooling_contribution",
        "heating2_contribution", "cooling2_contribution",
    )
    for row in term_rows:
        rkey = (
            int(row["record"]), int(row["data_type"]), int(row["rate_type"]),
            int(row["ion_index"]), int(row["ion_stage"]),
        )
        if rkey not in record_groups:
            record_groups[rkey] = {
                "source": "python", "element_z": int(element_z),
                "record": rkey[0], "data_type": rkey[1], "rate_type": rkey[2],
                "ion_index": rkey[3], "ion_stage": rkey[4], "term_count": 0,
                **{name: 0.0 for name in channels},
            }
        dst = record_groups[rkey]
        dst["term_count"] += 1
        for name in channels:
            dst[name] += float(row[name])

        tkey = (int(row["data_type"]), int(row["rate_type"]))
        if tkey not in type_groups:
            type_groups[tkey] = {
                "source": "python", "element_z": int(element_z),
                "data_type": tkey[0], "rate_type": tkey[1], "term_count": 0,
                "record_ids": set(), **{name: 0.0 for name in channels},
            }
        tdst = type_groups[tkey]
        tdst["term_count"] += 1
        tdst["record_ids"].add(int(row["record"]))
        for name in channels:
            tdst[name] += float(row[name])

    record_rows = []
    for row in record_groups.values():
        row = dict(row)
        row["absolute_thermal_contribution"] = sum(float(row[name]) for name in channels)
        record_rows.append(row)
    record_rows.sort(key=lambda row: (-float(row["absolute_thermal_contribution"]), int(row["record"])))

    type_rows = []
    for row in type_groups.values():
        out = dict(row)
        ids = out.pop("record_ids")
        out["record_count"] = len(ids)
        out["absolute_thermal_contribution"] = sum(float(out[name]) for name in channels)
        type_rows.append(out)
    type_rows.sort(key=lambda row: (int(row["data_type"]), int(row["rate_type"])))

    return {
        "stage_fractions": stage_rows,
        "preliminary_stage_rates": preliminary_stage_rows,
        "preliminary_records": preliminary_record_rows,
        "compact_populations": compact_rows,
        "electron_by_stage": electron_rows,
        "record_results": record_result_rows,
        "matrix_terms": all_matrix_terms,
        "thermal_terms": term_rows,
        "thermal_records": record_rows,
        "thermal_by_data_type": type_rows,
        "top_thermal_records": record_rows[:100],
    }


def write_python_call1_eval1_attribution(
    result: FixedStateCalcHMCAllResult,
    out_dir: str | Path,
    *,
    element_z: int = 20,
) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = python_element_attribution_rows(result, element_z=element_z)
    paths: dict[str, str] = {}
    for name, payload in rows.items():
        path = out / f"python_z{element_z}_{name}.csv"
        _write_rows(path, payload)
        paths[name] = str(path)
    summary = {
        "schema": "xstar-tools-v06481221-python-call1-eval1-attribution-v1",
        "element_z": int(element_z),
        "temperature_k": float(result.temperature_k),
        "electron_fraction_input": float(result.electron_fraction_xee),
        "files": paths,
    }
    summary_path = out / f"python_z{element_z}_attribution_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["summary"] = str(summary_path)
    return paths


__all__ = [
    "python_element_attribution_rows",
    "write_python_call1_eval1_attribution",
]
