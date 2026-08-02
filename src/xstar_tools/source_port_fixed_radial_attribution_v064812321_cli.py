"""Replay one captured C++ accepted-radial fixed state in the source-faithful Python evaluator.

Diagnostic only.  The captured C++ state is treated as the entry state; no
radial controller, convergence iteration, publication writer, or product state
is executed here.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from .xstar import physical_runner as pr
from .xstar.dsec import DsecMutableRuntimeState
from .xstar.element_equilibrium import EscapeProbabilityContext
from .xstar.local_zone import FixedStateElementRequest, calc_hmc_all
from .xstar.fixed_state_attribution import python_element_attribution_rows, _write_rows
from .xstar.radiation import apply_bremsmap_to_state
from .xstar.ucalc import default_source_faithful_ucalc


def _manifest(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {str(row["key"]): str(row["value"]) for row in rows}


def _read(path: Path, count: int) -> np.ndarray:
    arr = np.fromfile(path, dtype=np.float64)
    if arr.size != count:
        raise RuntimeError(f"{path.name}: expected {count} doubles, found {arr.size}")
    return arr


def _tau_physical(values: np.ndarray, expected: int) -> np.ndarray:
    if values.size == expected + 1:
        return values[1:].copy()
    if values.size >= expected:
        return values[:expected].copy()
    out = np.zeros(expected, dtype=float)
    out[: values.size] = values
    return out


def _line_tau_source_domain(
    values: np.ndarray, expected: int, active_max_line: int
) -> tuple[np.ndarray, str]:
    """Project native runtime line tau onto Python's full source line domain.

    Native C++ uses ``runtime_line_tau[line_index_one_based - 1]`` and allocates
    ``maximum_active_line_index + 1`` slots.  The final native slot is spare
    capacity, not source line ``maximum_active_line_index + 1``.  Python keeps
    the complete source ``1:nlsvn`` domain.  Copy exactly the source-aligned
    active prefix (lines 1..active_max_line), discard the native spare slot,
    and zero-extend the inactive ATDB tail.
    """
    if expected < 0 or active_max_line < 0 or active_max_line > expected:
        raise RuntimeError(
            f"invalid line domain: active_max={active_max_line}, source_count={expected}"
        )
    raw = np.asarray(values, dtype=float).reshape(-1)
    if raw.size < active_max_line:
        raise RuntimeError(
            f"native line-tau prefix has {raw.size} slots but source line {active_max_line} is required"
        )
    out = np.zeros(expected, dtype=float)
    if active_max_line:
        out[:active_max_line] = raw[:active_max_line]
    if active_max_line == expected:
        return out, "active_prefix_exact_source_domain"
    return out, "active_prefix_zero_extend"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-script", required=True)
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--coheat-data", required=True)
    parser.add_argument("--capture-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--element-z", type=int, default=20)
    args = parser.parse_args(argv)

    capture = Path(args.capture_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = _manifest(capture / "manifest.csv")
    required_schema = "xstar-tools-v064812321-fixed-radial-input-v1"
    if meta.get("schema") != required_schema:
        raise RuntimeError(f"unexpected capture schema: {meta.get('schema')!r}")

    resolved_atdb = pr._resolve_runner_atdb_path(args.atdb)
    normalized = pr.normalize_xstar_parameters(pr.parse_run_xstar_script(args.run_script))
    pointer_cache, metadata_cache = pr._cache_paths(resolved_atdb, args.cache_dir)
    state, built = pr._build_initial_state(
        normalized,
        atdb_path=resolved_atdb,
        coheat_path=args.coheat_data,
        pointer_cache=pointer_cache,
        metadata_cache=metadata_cache,
        use_cache=True,
        rebuild_cache=False,
        progress_callback=None,
    )
    try:
        nrad = int(meta["radiation_bin_count"])
        ndsec = int(meta["dsec_radiation_bin_count"])
        ntau = int(meta["continuum_tau_count"])
        nline_tau = int(meta.get("line_tau_count", "0"))
        nglobal = int(meta["global_level_count"])
        full_energy = _read(capture / "dsec_radiation_energy_ev.bin", ndsec)
        full_bremsa = _read(capture / "dsec_bremsa.bin", ndsec)
        if ndsec != int(state.control["ncn2"]):
            raise RuntimeError(
                f"captured DSEC grid has {ndsec} bins; Python source state expects {state.control['ncn2']}"
            )
        state.radiation.epi = full_energy.copy()
        state.radiation.bremsa = full_bremsa.copy()
        state.radiation.bremsint = np.zeros(ndsec, dtype=float)
        state.radiation.bremsam = np.zeros(ndsec, dtype=float)
        apply_bremsmap_to_state(state)

        derived = state.atomic.derived
        n_lines = int(derived.nlsvn)
        n_cont = int(derived.ncsvn)
        tau_in_raw = _read(capture / "continuum_tau_in.bin", ntau)
        tau_out_raw = _read(capture / "continuum_tau_out.bin", ntau)
        line_tau_in_raw = _read(capture / "line_tau_in.bin", nline_tau) if nline_tau else np.zeros(0, dtype=float)
        line_tau_out_raw = _read(capture / "line_tau_out.bin", nline_tau) if nline_tau else np.zeros(0, dtype=float)
        active_subset = state.control.get("active_atdb_subset")
        active_line_indices = np.asarray(
            getattr(active_subset, "line_indices", ()), dtype=np.int64
        ).reshape(-1) if active_subset is not None else np.zeros(0, dtype=np.int64)
        active_max_line = int(active_line_indices.max()) if active_line_indices.size else 0
        # Native storage is zero based by source line_index-1.  A native prefix
        # of length N therefore covers source line indices 1..N.
        if active_max_line > nline_tau:
            raise RuntimeError(
                f"captured line-tau prefix has {nline_tau} slots but active source line index {active_max_line} is required"
            )
        line_tau_in, line_tau_mode_in = _line_tau_source_domain(
            line_tau_in_raw, n_lines, active_max_line
        )
        line_tau_out, line_tau_mode_out = _line_tau_source_domain(
            line_tau_out_raw, n_lines, active_max_line
        )
        if line_tau_mode_in != line_tau_mode_out:
            raise RuntimeError(
                f"line-tau domain projection mismatch: inward={line_tau_mode_in}, outward={line_tau_mode_out}"
            )
        print(f"V064812321_CAPTURED_LINE_TAU_COUNT={nline_tau}")
        print(f"V064812321_PYTHON_SOURCE_LINE_TAU_COUNT={n_lines}")
        print(f"V064812321_ACTIVE_MAX_LINE_INDEX={active_max_line}")
        print(f"V064812321_LINE_TAU_DOMAIN_PROJECTION={line_tau_mode_in.upper()}")
        print("V064812321_LINE_TAU_SOURCE_INDEX_ALIGNMENT=ACCEPT")
        escape = EscapeProbabilityContext(
            line_tau_in=line_tau_in,
            line_tau_out=line_tau_out,
            continuum_tau_in=_tau_physical(tau_in_raw, n_cont),
            continuum_tau_out=_tau_physical(tau_out_raw, n_cont),
            allow_missing_as_zero=False,
        )
        radiation = SimpleNamespace(
            epi=np.asarray(state.radiation.epi, dtype=float),
            bremsa=np.asarray(state.radiation.bremsa, dtype=float),
            epim=np.asarray(state.radiation.epim, dtype=float),
            epim_eV=np.asarray(state.radiation.epim, dtype=float),
            bremsam=np.asarray(state.radiation.bremsam, dtype=float),
            bremsint=np.asarray(state.radiation.bremsint, dtype=float),
        )
        xilevg = _read(capture / "global_xilevg.bin", nglobal) if nglobal else np.zeros(0)
        bilevg = _read(capture / "global_bilevg.bin", nglobal) if nglobal else np.zeros(0)
        rnisg = _read(capture / "global_rnisg.bin", nglobal) if nglobal else np.zeros(0)
        global_level_index_by_key = {
            (int(k[0]), int(k[1]), int(k[2])): int(v)
            for k, v in dict(getattr(active_subset, "global_level_index_by_key", {})).items()
        }
        captured_global_populations = {
            key: float(xilevg[index - 1])
            for key, index in global_level_index_by_key.items()
            if 1 <= int(index) <= xilevg.size
        }
        if xilevg.size and not captured_global_populations:
            raise RuntimeError(
                "captured dense global_xilevg is nonempty but no source global-level mapping was resolved"
            )
        requests: list[FixedStateElementRequest] = []
        required: list[int] = []
        for z, abundance in enumerate(normalized.physical_abundances, start=1):
            if float(abundance) <= 1.0e-24:
                continue
            required.append(z)
            requests.append(
                FixedStateElementRequest(
                    element_z=z,
                    min_ion_stage=1,
                    max_ion_stage=z + 1,
                    abundance=float(abundance),
                    radiation=radiation,
                    escape=escape,
                    covering_fraction=float(normalized.get("cfrac")),
                    turbulent_velocity_km_s=float(normalized.get("vturbi")),
                    lfast=2,
                    critf=float(normalized.get("critf")),
                    use_source_ion_limits=True,
                    initial_global_populations={
                        key: value for key, value in captured_global_populations.items()
                        if int(key[0]) == int(z)
                    },
                    initial_population_source="v064812321_cpp_fixed_radial_capture",
                    terminal_continuum_seed_mode="source-zero",
                    strict_context=True,
                    allow_lstsq_fallback=False,
                    allow_dense_matrix_rescue=False,
                )
            )

        runtime = DsecMutableRuntimeState(
            temperature_t4=float(meta["temperature_k"]) / 1.0e4,
            electron_fraction_xee=float(meta["electron_fraction_xee"]),
            hydrogen_density_cm3=float(meta["hydrogen_density_cm3"]),
            element_requests=tuple(requests),
            required_element_z=tuple(required),
            pressure=float(normalized.pressure_dyn_cm2),
            lcdd=int(normalized.lcdd),
            global_level_populations=dict(captured_global_populations),
            global_level_index_by_key=dict(global_level_index_by_key),
            global_xilevg_by_index=xilevg.copy() if xilevg.size else None,
            global_bilevg_by_index=bilevg.copy() if bilevg.size else None,
            global_rnisg_by_index=rnisg.copy() if rnisg.size else None,
            source_global_alias_writeback=True,
            reset_leveltemp_each_calc_hmc_all=True,
            retain_source_arrays=True,
        )
        # The continuum contexts are source-faithful Python translations built
        # from the captured full radiation field and the source bremsmap.
        table = pr.load_compton_table(args.coheat_data, atdb_path=resolved_atdb)
        kwargs = dict(pr._calc_kwargs_factory(state, table)(runtime))
        result = calc_hmc_all(
            state.atomic.master,
            state.atomic.derived,
            elements=tuple(requests),
            temperature_k=float(meta["temperature_k"]),
            hydrogen_density_cm3=float(meta["hydrogen_density_cm3"]),
            electron_fraction_xee=float(meta["electron_fraction_xee"]),
            pressure=float(normalized.pressure_dyn_cm2),
            lcdd=int(normalized.lcdd),
            required_element_z=tuple(required),
            dispatcher=default_source_faithful_ucalc(),
            initial_leveltemp_workspace=None,
            initial_leveltemp_owner_by_column={},
            initial_global_xilevg_by_index=xilevg if xilevg.size else None,
            initial_global_bilevg_by_index=bilevg if bilevg.size else None,
            initial_global_rnisg_by_index=rnisg if rnisg.size else None,
            source_global_alias_writeback=True,
            **kwargs,
        )
        rows = python_element_attribution_rows(result, element_z=args.element_z)
        paths: dict[str, str] = {}
        for name, payload in rows.items():
            path = out / f"python_z{args.element_z}_{name}.csv"
            _write_rows(path, payload)
            paths[name] = str(path)
        summary = {
            "schema": "xstar-tools-v064812321-python-fixed-radial-attribution-v1",
            "source_sequence": int(meta["source_sequence"]),
            "element_z": int(args.element_z),
            "captured_line_tau_count": int(nline_tau),
            "python_source_line_tau_count": int(n_lines),
            "active_max_line_index": int(active_max_line),
            "line_tau_domain_projection": str(line_tau_mode_in),
            "captured_global_population_keys": int(len(captured_global_populations)),
            "captured_global_population_sum": float(sum(captured_global_populations.values())),
            "temperature_k": float(result.temperature_k),
            "electron_fraction_input": float(result.electron_fraction_xee),
            "hmctot": float(result.hmctot),
            "elcter": float(result.elcter),
            "files": paths,
        }
        (out / "python_fixed_radial_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print("V064812321_PYTHON_FIXED_RADIAL_REPLAY=ACCEPT")
        print(f"V064812321_PYTHON_FIXED_RADIAL_SEQUENCE={meta['source_sequence']}")
        print(f"V064812321_PYTHON_FIXED_RADIAL_T={result.temperature_k:.17g}")
        print(f"V064812324_PYTHON_CAPTURED_GLOBAL_POPULATION_KEYS={len(captured_global_populations)}")
        print(f"V064812324_PYTHON_CAPTURED_GLOBAL_POPULATION_SUM={sum(captured_global_populations.values()):.17g}")
        return 0
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
