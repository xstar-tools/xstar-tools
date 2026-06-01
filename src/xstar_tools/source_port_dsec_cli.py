"""Command-line tools for the source-faithful ``dsec`` translation."""
from __future__ import annotations

import argparse
from pathlib import Path

from .xstar import (
    DsecEvaluation,
    DsecMutableRuntimeState,
    compare_dsec_trajectory,
    dsec,
    load_python_dsec_trajectory,
    load_xstar_dsec_trajectory,
    validate_v0444_complete_fixed_state_regression,
    write_dsec_trajectory_parity_products,
    write_dsec_trajectory_products,
)


class _SyntheticBalance:
    def __init__(self, target_t4: float, target_xee: float):
        self.target_t4 = float(target_t4)
        self.target_xee = float(target_xee)

    def __call__(self, state: DsecMutableRuntimeState) -> DsecEvaluation:
        return DsecEvaluation(
            hmctot=(self.target_t4 - state.temperature_t4) / self.target_t4,
            elcter=state.electron_fraction_xee - self.target_xee,
            diagnostics={"synthetic_branch_test": True},
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run synthetic dsec branch tests or compare a Python/XSTAR trajectory."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    smoke = sub.add_parser("synthetic", help="run the deterministic synthetic branch test")
    smoke.add_argument("--temperature-t4", type=float, default=1.0)
    smoke.add_argument("--electron-fraction-xee", type=float, default=1.44)
    smoke.add_argument("--hydrogen-density-cm3", type=float, default=1.0e8)
    smoke.add_argument("--target-temperature-t4", type=float, default=2.0)
    smoke.add_argument("--target-electron-fraction-xee", type=float, default=1.0)
    smoke.add_argument("--nlim", type=int, default=20)
    smoke.add_argument("--tinf-t4", type=float, default=0.01)
    smoke.add_argument("--out-dir", type=Path, required=True)

    compare = sub.add_parser("compare", help="compare saved Python and XSTAR trajectories")
    compare.add_argument("--python-trajectory", type=Path, required=True)
    compare.add_argument("--xstar-trajectory", type=Path, required=True)
    compare.add_argument("--xstar-dsec-call-id", type=int, default=1)
    compare.add_argument("--runtime-rtol", type=float, default=5.0e-12)
    compare.add_argument("--runtime-atol", type=float, default=1.0e-30)
    compare.add_argument("--residual-rtol", type=float, default=5.0e-3)
    compare.add_argument("--thermal-residual-atol", type=float, default=1.0e-8)
    compare.add_argument("--charge-residual-atol", type=float, default=1.0e-10)
    compare.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "synthetic":
        state = DsecMutableRuntimeState(
            temperature_t4=args.temperature_t4,
            electron_fraction_xee=args.electron_fraction_xee,
            hydrogen_density_cm3=args.hydrogen_density_cm3,
        )
        result = dsec(
            state,
            evaluator=_SyntheticBalance(
                args.target_temperature_t4,
                args.target_electron_fraction_xee,
            ),
            nlim=args.nlim,
            tinf_t4=args.tinf_t4,
        )
        products = write_dsec_trajectory_products(result, args.out_dir)
        frozen = validate_v0444_complete_fixed_state_regression()
        print(f"dsec_converged={result.converged}")
        print(f"ntotit={result.ntotit}")
        print(f"final_temperature_t4={result.state.temperature_t4:.17g}")
        print(f"final_electron_fraction_xee={result.state.electron_fraction_xee:.17g}")
        print(f"frozen_v0444_complete_fixed_state_regression={frozen.ready}")
        for name, path in products.items():
            print(f"{name}={path}")
        return 0 if result.converged and frozen.ready else 2

    python_result = load_python_dsec_trajectory(args.python_trajectory)
    xstar_reference = load_xstar_dsec_trajectory(
        args.xstar_trajectory, call_id=args.xstar_dsec_call_id
    )
    parity = compare_dsec_trajectory(
        python_result,
        xstar_reference,
        runtime_rtol=args.runtime_rtol,
        runtime_atol=args.runtime_atol,
        residual_rtol=args.residual_rtol,
        thermal_residual_atol=args.thermal_residual_atol,
        charge_residual_atol=args.charge_residual_atol,
    )
    products = write_dsec_trajectory_parity_products(parity, args.out_dir)
    print(f"dsec_trajectory_parity_ready={parity.ready}")
    print(f"event_sequence_ready={parity.event_sequence_ready}")
    print(f"thermal_residual_sign_ready={parity.thermal_residual_sign_ready}")
    print(f"charge_residual_sign_ready={parity.charge_residual_sign_ready}")
    for name, path in products.items():
        print(f"{name}={path}")
    return 0 if parity.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
