"""Capture exactly the first pure-Python fixed-state evaluation for all active elements."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

from .xstar.fixed_state_attribution import write_python_call1_eval1_attribution
from .xstar import physical_runner as pr
from .xstar.radial_transfer import run_bounded_radial_shell


class _CapturedFirstEvaluation(RuntimeError):
    pass


def _progress(event: str, details: dict[str, object]) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    payload = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
    print(f"[{stamp}] {event}" + (f" {payload}" if payload else ""), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture call-1/eval-1 pure-Python fixed-state attribution for all active elements"
    )
    parser.add_argument("--run-script", required=True)
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--coheat-data")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args(argv)

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
        progress_callback=_progress if args.progress else None,
    )
    captured: dict[str, object] = {}

    def gate(evaluation_index, snapshot, result):
        if int(evaluation_index) != 1:
            raise RuntimeError(f"expected first evaluation, got {evaluation_index}")
        captured["snapshot"] = snapshot
        captured["result"] = result
        raise _CapturedFirstEvaluation()

    state.control["zone1_dsec_capture_all_inputs"] = True
    state.control["zone1_dsec_evaluation_gate_callback"] = gate
    state.control["diagnostics_mode"] = "full"
    try:
        try:
            run_bounded_radial_shell(state, zone_index=1, pass_index=1, direction=-1, fixed_state=False)
        except _CapturedFirstEvaluation:
            pass
        result = captured.get("result")
        if result is None:
            print("V06481234_PYTHON_CALL1_EVAL1_CAPTURE=REJECT", file=sys.stderr)
            return 6

        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        element_zs = sorted(int(item.request.element_z) for item in result.element_results)
        manifest = {
            "schema": "xstar-tools-v06481234-python-call1-eval1-all-element-attribution-v1",
            "temperature_k": float(result.temperature_k),
            "electron_fraction_input": float(result.electron_fraction_xee),
            "element_zs": element_zs,
            "element_outputs": {},
        }
        for z in element_zs:
            paths = write_python_call1_eval1_attribution(result, out, element_z=z)
            manifest["element_outputs"][str(z)] = paths
        manifest_path = out / "python_all_element_attribution_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        print("V06481234_PYTHON_CALL1_EVAL1_CAPTURE=ACCEPT")
        print(f"V06481234_PYTHON_CALL1_EVAL1_TEMPERATURE_K={result.temperature_k:.17g}")
        print(f"V06481234_PYTHON_CALL1_EVAL1_XEE_INPUT={result.electron_fraction_xee:.17g}")
        print("V06481234_PYTHON_CALL1_EVAL1_ELEMENT_ZS=" + ";".join(map(str, element_zs)))
        print(f"V06481234_PYTHON_CALL1_EVAL1_MANIFEST={manifest_path}")
        return 0
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
