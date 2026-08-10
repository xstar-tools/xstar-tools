"""Correlation and matching-state loaders for physical ``dsec`` validation.

v0.4.48 separates the XSTAR state entering the first internal
``calc_hmc_all`` evaluation from the source-order post-``dsec`` reference.
The probe values remain regression/input-state oracles and never provide
precomputed rates, matrices, or residuals to the Python calculation.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np

from .dsec import DsecPortError
from .element_equilibrium import EscapeProbabilityContext
from .fortran_numbers import parse_fortran_float
from .ucalc import UCalcLevel, UCalcLevelTable
from ..xstar_live_rate_grid_probe import LiveRateGridState


@dataclass(frozen=True)
class CalcHMCAllCallCorrelation:
    calc_hmc_all_call_id: int
    dsec_call_id: int
    dsec_evaluation_index: int
    phase: str
    temperature_t4: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float


@dataclass(frozen=True)
class DsecCallCorrelation:
    dsec_call_id: int
    input_calc_hmc_all_call_id: int
    post_dsec_calc_hmc_all_call_id: int
    rows: Tuple[CalcHMCAllCallCorrelation, ...]
    source_path: str


@dataclass(frozen=True)
class DsecLevelTempSnapshot:
    """Complete raw XSTAR ``leveltemp`` work array at one call boundary.

    The production Python evaluator currently exposes the source-used subset
    through :class:`UCalcLevelTable`.  v0.4.51 also preserves all ten real and
    integer slots plus ``nlpt``/``iltp`` so transition diagnostics never lose
    captured XSTAR state.
    """

    rlev: np.ndarray
    ilev: np.ndarray
    nlpt: np.ndarray
    iltp: np.ndarray

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the n columns operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def n_columns(self) -> int:
        return int(self.rlev.shape[1]) if self.rlev.ndim == 2 else 0


@dataclass(frozen=True)
class DsecMatchingInputState:
    calc_hmc_all_call_id: int
    dsec_call_id: int
    dsec_evaluation_index: int
    phase: str
    temperature_t4: float
    trad: float
    radius_cm: float
    zone_thickness_cm: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    covering_fraction: float
    pressure: float
    lcdd: int
    zeta: float
    turbulent_velocity_km_s: float
    critf: float
    ncn2: int
    radiation: LiveRateGridState
    escape: EscapeProbabilityContext
    global_level_values_by_index: np.ndarray
    global_bilev_values_by_index: np.ndarray
    global_rnist_values_by_index: np.ndarray
    leveltemp_workspace: Optional[UCalcLevelTable]
    leveltemp_snapshot: Optional[DsecLevelTempSnapshot]
    source_dir: str

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the global xilevg is zero operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def global_xilevg_is_zero(self) -> bool:
        return bool(np.count_nonzero(self.global_level_values_by_index) == 0)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Read rows for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise DsecPortError(f"missing XSTAR matching-state probe: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load calc hmc all call correlation for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def load_calc_hmc_all_call_correlation(
    path: str | Path,
) -> Tuple[CalcHMCAllCallCorrelation, ...]:
    target = Path(path)
    if target.is_dir():
        target = target / "xstar_dsec_calc_hmc_all_call_correlation.csv"
    rows = _read_rows(target)
    result = []
    for row in rows:
        result.append(
            CalcHMCAllCallCorrelation(
                calc_hmc_all_call_id=int(row["calc_hmc_all_call_id"]),
                dsec_call_id=int(row["dsec_call_id"]),
                dsec_evaluation_index=int(row["dsec_evaluation_index"]),
                phase=str(row["phase"]).strip(),
                temperature_t4=parse_fortran_float(row["temperature_t4"]),
                electron_fraction_xee=parse_fortran_float(
                    row["electron_fraction_xee"]
                ),
                hydrogen_density_cm3=parse_fortran_float(
                    row["hydrogen_density_cm3"]
                ),
            )
        )
    return tuple(result)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Resolve dsec calc hmc all calls for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def resolve_dsec_calc_hmc_all_calls(
    path: str | Path,
    *,
    dsec_call_id: int,
    input_evaluation_index: int = 1,
) -> DsecCallCorrelation:
    rows = load_calc_hmc_all_call_correlation(path)
    matching = tuple(row for row in rows if row.dsec_call_id == int(dsec_call_id))
    inputs = [
        row
        for row in matching
        if row.phase == "dsec_internal"
        and row.dsec_evaluation_index == int(input_evaluation_index)
    ]
    finals = [row for row in matching if row.phase == "post_dsec"]
    if len(inputs) != 1:
        raise DsecPortError(
            "expected exactly one correlated first internal calc_hmc_all call for "
            f"dsec_call_id={dsec_call_id}, evaluation={input_evaluation_index}; "
            f"observed={[(r.calc_hmc_all_call_id, r.phase, r.dsec_evaluation_index) for r in inputs]}"
        )
    if len(finals) != 1:
        raise DsecPortError(
            "expected exactly one correlated post-dsec calc_hmc_all call for "
            f"dsec_call_id={dsec_call_id}; observed="
            f"{[(r.calc_hmc_all_call_id, r.phase) for r in finals]}"
        )
    source = Path(path)
    if source.is_dir():
        source = source / "xstar_dsec_calc_hmc_all_call_correlation.csv"
    return DsecCallCorrelation(
        dsec_call_id=int(dsec_call_id),
        input_calc_hmc_all_call_id=inputs[0].calc_hmc_all_call_id,
        post_dsec_calc_hmc_all_call_id=finals[0].calc_hmc_all_call_id,
        rows=matching,
        source_path=str(source),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Select call for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def _select_call(rows: Iterable[Mapping[str, str]], call_id: int) -> list[Mapping[str, str]]:
    return [row for row in rows if int(row["calc_hmc_all_call_id"]) == int(call_id)]


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the dense pair operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def _dense_pair(
    rows: Sequence[Mapping[str, str]],
    *,
    index_field: str,
    first_field: str,
    second_field: str,
) -> tuple[np.ndarray, np.ndarray]:
    if not rows:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=float)
    n = max(int(row[index_field]) for row in rows)
    first = np.zeros(n, dtype=float)
    second = np.zeros(n, dtype=float)
    for row in rows:
        idx = int(row[index_field]) - 1
        first[idx] = parse_fortran_float(row[first_field])
        second[idx] = parse_fortran_float(row[second_field])
    return first, second


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load leveltemp for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def _load_leveltemp(rows: Sequence[Mapping[str, str]]) -> Optional[UCalcLevelTable]:
    if not rows:
        return None
    by_column: Dict[int, Dict[int, tuple[float, int]]] = {}
    nlpt: Dict[int, int] = {}
    iltp: Dict[int, int] = {}
    for row in rows:
        column = int(row["column_index"])
        slot = int(row["slot"])
        by_column.setdefault(column, {})[slot] = (
            parse_fortran_float(row["rlev"]),
            int(row["ilev"]),
        )
        nlpt[column] = int(row["nlpt"])
        iltp[column] = int(row["iltp"])
    levels: Dict[int, UCalcLevel] = {}
    for column, slots in by_column.items():
        r = {slot: value[0] for slot, value in slots.items()}
        i = {slot: value[1] for slot, value in slots.items()}
        if not any(value != 0.0 for value in r.values()) and not any(
            value != 0 for value in i.values()
        ) and nlpt.get(column, 0) == 0 and iltp.get(column, 0) == 0:
            continue
        levels[column] = UCalcLevel(
            index=column,
            energy_ev=float(r.get(1, 0.0)),
            statistical_weight=float(r.get(2, 0.0)),
            # ucalc.f90 reads rlev(4) for the bound/continuum energy.
            # rlev(3) is preserved only in the raw v0.4.51 snapshot.
            ionization_potential_ev=float(r.get(4, 0.0)),
            continuum_energy_ev=float(r.get(4, 0.0)),
            principal_n=(None if i.get(1, 0) == 0 else int(i[1])),
            orbital_l=(None if i.get(3, 0) == 0 else int(i[3])),
        )
    return UCalcLevelTable(levels=levels, nlev=max(levels, default=0))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load leveltemp snapshot for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def _load_leveltemp_snapshot(
    rows: Sequence[Mapping[str, str]],
) -> Optional[DsecLevelTempSnapshot]:
    if not rows:
        return None
    n = max(int(row["column_index"]) for row in rows)
    rlev = np.zeros((10, n), dtype=float)
    ilev = np.zeros((10, n), dtype=int)
    nlpt = np.zeros(n, dtype=int)
    iltp = np.zeros(n, dtype=int)
    for row in rows:
        column = int(row["column_index"]) - 1
        slot = int(row["slot"]) - 1
        if not (0 <= slot < 10):
            raise DsecPortError(f"invalid leveltemp slot {slot + 1}")
        rlev[slot, column] = parse_fortran_float(row["rlev"])
        ilev[slot, column] = int(row["ilev"])
        nlpt[column] = int(row["nlpt"])
        iltp[column] = int(row["iltp"])
    return DsecLevelTempSnapshot(rlev=rlev, ilev=ilev, nlpt=nlpt, iltp=iltp)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load dsec matching input state for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def load_dsec_matching_input_state(
    probe_dir: str | Path,
    *,
    call_id: int,
) -> DsecMatchingInputState:
    root = Path(probe_dir)
    summary_rows = _select_call(
        _read_rows(root / "xstar_calc_hmc_all_input_summary_probe.csv"), call_id
    )
    if len(summary_rows) != 1:
        raise DsecPortError(
            f"expected one input summary for calc_hmc_all_call_id={call_id}; "
            f"observed={len(summary_rows)}"
        )
    summary = summary_rows[0]

    continuum_rows = _select_call(
        _read_rows(root / "xstar_calc_hmc_all_input_continuum_probe.csv"), call_id
    )
    continuum_rows.sort(key=lambda row: int(row["grid_index"]))
    ncn2 = int(summary["ncn2"])
    if len(continuum_rows) != ncn2:
        raise DsecPortError(
            f"input continuum row count {len(continuum_rows)} does not match ncn2={ncn2}"
        )
    epi = tuple(parse_fortran_float(row["epi_eV"]) for row in continuum_rows)
    bremsa = tuple(parse_fortran_float(row["bremsa"]) for row in continuum_rows)
    bremsint = tuple(parse_fortran_float(row["bremsint"]) for row in continuum_rows)
    radiation = LiveRateGridState(
        zone_index=-1,
        pass_index=-1,
        ldir=0,
        ncn2m=ncn2,
        epim_eV=epi,
        bremsam=bremsa,
        bremsint=bremsint,
        metadata={
            "capture_index": 1,
            "calc_hmc_all_call_id": int(call_id),
            "dsec_call_id": int(summary["dsec_call_id"]),
            "dsec_evaluation_index": int(summary["dsec_evaluation_index"]),
            "source": "xstar_calc_hmc_all_input_continuum_probe",
        },
    )

    tau0_rows = _select_call(
        _read_rows(root / "xstar_calc_hmc_all_input_tau0_probe.csv"), call_id
    )
    tauc_rows = _select_call(
        _read_rows(root / "xstar_calc_hmc_all_input_tauc_probe.csv"), call_id
    )
    line_in, line_out = _dense_pair(
        tau0_rows,
        index_field="line_index",
        first_field="tau_in",
        second_field="tau_out",
    )
    cont_in, cont_out = _dense_pair(
        tauc_rows,
        index_field="continuum_index",
        first_field="tau_in",
        second_field="tau_out",
    )
    escape = EscapeProbabilityContext(
        line_tau_in=line_in,
        line_tau_out=line_out,
        continuum_tau_in=cont_in,
        continuum_tau_out=cont_out,
        allow_missing_as_zero=False,
    )

    global_rows = _select_call(
        _read_rows(root / "xstar_calc_hmc_all_input_global_levels_probe.csv"),
        call_id,
    )
    nlevel = max((int(row["global_level_index"]) for row in global_rows), default=0)
    xilev = np.zeros(nlevel, dtype=float)
    bilev = np.zeros(nlevel, dtype=float)
    rnist = np.zeros(nlevel, dtype=float)
    for row in global_rows:
        idx = int(row["global_level_index"]) - 1
        xilev[idx] = parse_fortran_float(row["xilevg"])
        bilev[idx] = parse_fortran_float(row["bilevg"])
        rnist[idx] = parse_fortran_float(row["rnisg"])

    leveltemp_rows = _select_call(
        _read_rows(root / "xstar_calc_hmc_all_input_leveltemp_probe.csv"), call_id
    )
    return DsecMatchingInputState(
        calc_hmc_all_call_id=int(call_id),
        dsec_call_id=int(summary["dsec_call_id"]),
        dsec_evaluation_index=int(summary["dsec_evaluation_index"]),
        phase=str(summary["phase"]).strip(),
        temperature_t4=parse_fortran_float(summary["temperature_t4"]),
        trad=parse_fortran_float(summary["trad"]),
        radius_cm=parse_fortran_float(summary["radius_cm"]),
        zone_thickness_cm=parse_fortran_float(summary["zone_thickness_cm"]),
        electron_fraction_xee=parse_fortran_float(summary["electron_fraction_xee"]),
        hydrogen_density_cm3=parse_fortran_float(summary["hydrogen_density_cm3"]),
        covering_fraction=parse_fortran_float(summary["covering_fraction"]),
        pressure=parse_fortran_float(summary["pressure"]),
        lcdd=int(summary["lcdd"]),
        zeta=parse_fortran_float(summary["zeta"]),
        turbulent_velocity_km_s=parse_fortran_float(
            summary["turbulent_velocity_km_s"]
        ),
        critf=parse_fortran_float(summary["critf"]),
        ncn2=ncn2,
        radiation=radiation,
        escape=escape,
        global_level_values_by_index=xilev,
        global_bilev_values_by_index=bilev,
        global_rnist_values_by_index=rnist,
        leveltemp_workspace=_load_leveltemp(leveltemp_rows),
        leveltemp_snapshot=_load_leveltemp_snapshot(leveltemp_rows),
        source_dir=str(root),
    )


@dataclass(frozen=True)
class DsecThermalDecompositionRow:
    dsec_call_id: int
    evaluation_index: int
    calc_hmc_all_call_id: int
    phase: str
    values: Mapping[str, float]


_THERMAL_FIELDS = (
    "temperature_t4",
    "temperature_k",
    "electron_fraction_xee",
    "hydrogen_density_cm3",
    "httot_pre_continuum",
    "cltot_pre_continuum",
    "httot2_pre_continuum",
    "cltot2_pre_continuum",
    "htcomp",
    "clcomp",
    "htfreef",
    "clbrems",
    "httot",
    "cltot",
    "httot2",
    "cltot2",
    "cllines",
    "clcont",
    "hmctot",
    "elcter",
)

# ``cllines`` and ``clcont`` are written by the XSTAR probe to preserve the
# complete source decomposition.  The current Python fixed-state result does
# not expose them as independent public scalars, so the strict v0.4.48 parity
# gate compares only quantities owned by both implementations.
_THERMAL_COMPARE_FIELDS = tuple(
    name for name in _THERMAL_FIELDS if name not in {"cllines", "clcont"}
)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load xstar dsec thermal decomposition for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def load_xstar_dsec_thermal_decomposition(
    path: str | Path,
    *,
    dsec_call_id: int,
) -> Tuple[DsecThermalDecompositionRow, ...]:
    target = Path(path)
    if target.is_dir():
        target = target / "xstar_dsec_thermal_decomposition_probe.csv"
    rows = _read_rows(target)
    result = []
    for row in rows:
        if int(row["dsec_call_id"]) != int(dsec_call_id):
            continue
        result.append(
            DsecThermalDecompositionRow(
                dsec_call_id=int(row["dsec_call_id"]),
                evaluation_index=int(row["evaluation_index"]),
                calc_hmc_all_call_id=int(row["calc_hmc_all_call_id"]),
                phase=str(row["phase"]).strip(),
                values={name: parse_fortran_float(row[name]) for name in _THERMAL_FIELDS},
            )
        )
    result.sort(key=lambda item: item.evaluation_index)
    return tuple(result)


@dataclass(frozen=True)
class DsecThermalParityRow:
    evaluation_index: int
    quantity: str
    python_value: float
    xstar_value: float
    absolute_difference: float
    relative_difference: float
    within_tolerance: bool


@dataclass(frozen=True)
class DsecThermalParityResult:
    rows: Tuple[DsecThermalParityRow, ...]
    n_python_evaluations: int
    n_xstar_evaluations: int
    evaluation_count_ready: bool
    thermal_decomposition_ready: bool
    max_absolute_difference: float
    max_relative_difference: float

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Report whether all prerequisites/results required by this stage are present and internally consistent.
    # Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def ready(self) -> bool:
        return bool(self.evaluation_count_ready and self.thermal_decomposition_ready)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the python thermal values operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def _python_thermal_values(evaluation: object) -> Mapping[str, float]:
    result = getattr(evaluation, "fixed_state_result", None)
    if result is None:
        raise DsecPortError("Python dsec evaluation is missing fixed_state_result")
    continuum = result.continuum
    return {
        "temperature_t4": float(result.temperature_k) / 1.0e4,
        "temperature_k": float(result.temperature_k),
        "electron_fraction_xee": float(result.electron_fraction_xee),
        "hydrogen_density_cm3": float(result.hydrogen_density_cm3),
        "httot_pre_continuum": float(result.httot_pre_continuum),
        "cltot_pre_continuum": float(result.cltot_pre_continuum),
        "httot2_pre_continuum": float(result.httot2_pre_continuum),
        "cltot2_pre_continuum": float(result.cltot2_pre_continuum),
        "htcomp": float(continuum.htcomp),
        "clcomp": float(continuum.clcomp),
        "htfreef": float(continuum.htfreef),
        "clbrems": float(continuum.clbrems),
        "httot": float(result.httot),
        "cltot": float(result.cltot),
        "httot2": float(result.httot2),
        "cltot2": float(result.cltot2),
        "cllines": float("nan"),
        "clcont": float("nan"),
        "hmctot": float(result.hmctot),
        "elcter": float(result.elcter),
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Compare dsec thermal decomposition for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def compare_dsec_thermal_decomposition(
    python_evaluations: Sequence[object],
    xstar_rows: Sequence[DsecThermalDecompositionRow],
    *,
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    prefix_mode: bool = False,
) -> DsecThermalParityResult:
    n_python = len(python_evaluations)
    n_xstar = len(xstar_rows)
    count_ready = n_python <= n_xstar if prefix_mode else n_python == n_xstar
    rows: list[DsecThermalParityRow] = []
    for index, (python_evaluation, xstar_row) in enumerate(
        zip(python_evaluations, xstar_rows), start=1
    ):
        py = _python_thermal_values(python_evaluation)
        for quantity in _THERMAL_COMPARE_FIELDS:
            pval = float(py[quantity])
            xval = float(xstar_row.values[quantity])
            absolute = abs(pval - xval)
            relative = absolute / max(abs(xval), 1.0e-300)
            ready = bool(np.isclose(pval, xval, rtol=rtol, atol=atol))
            rows.append(
                DsecThermalParityRow(
                    evaluation_index=index,
                    quantity=quantity,
                    python_value=pval,
                    xstar_value=xval,
                    absolute_difference=absolute,
                    relative_difference=relative,
                    within_tolerance=ready,
                )
            )
    decomposition_ready = bool(rows) and all(row.within_tolerance for row in rows)
    return DsecThermalParityResult(
        rows=tuple(rows),
        n_python_evaluations=n_python,
        n_xstar_evaluations=n_xstar,
        evaluation_count_ready=count_ready,
        thermal_decomposition_ready=decomposition_ready,
        max_absolute_difference=max((row.absolute_difference for row in rows), default=0.0),
        max_relative_difference=max((row.relative_difference for row in rows), default=0.0),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write dsec thermal parity products for this module while preserving the surrounding source/runtime invariants.
# Reference context: Qualification/diagnostic view of XSTAR dsec state; no separate paper equation.
# XSTAR-FUNCTION-COMMENT-END
def write_dsec_thermal_parity_products(
    parity: DsecThermalParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.48",
) -> Mapping[str, Path]:
    import json

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_dsec_thermal_decomposition_parity.csv"
    fields = tuple(DsecThermalParityRow.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in parity.rows:
            writer.writerow({name: getattr(row, name) for name in fields})
    summary = {
        "port_version": port_version,
        "n_python_evaluations": parity.n_python_evaluations,
        "n_xstar_evaluations": parity.n_xstar_evaluations,
        "evaluation_count_ready": parity.evaluation_count_ready,
        "thermal_decomposition_ready": parity.thermal_decomposition_ready,
        "dsec_thermal_parity_ready": parity.ready,
        "max_absolute_difference": parity.max_absolute_difference,
        "max_relative_difference": parity.max_relative_difference,
    }
    json_path = out / "xstar_dsec_thermal_decomposition_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_dsec_thermal_decomposition_parity_summary.md"
    md_path.write_text(
        "# Dsec thermal-decomposition parity\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


__all__ = [
    "CalcHMCAllCallCorrelation",
    "DsecCallCorrelation",
    "DsecLevelTempSnapshot",
    "DsecMatchingInputState",
    "DsecThermalDecompositionRow",
    "DsecThermalParityRow",
    "DsecThermalParityResult",
    "load_calc_hmc_all_call_correlation",
    "resolve_dsec_calc_hmc_all_calls",
    "load_dsec_matching_input_state",
    "load_xstar_dsec_thermal_decomposition",
    "compare_dsec_thermal_decomposition",
    "write_dsec_thermal_parity_products",
]
