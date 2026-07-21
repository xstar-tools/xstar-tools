"""Patch 5.20.5.1 source-oracle capture for literal Type-49 ``xstarsetup`` errc.

This module reuses the accepted patch-5.20.3.1 all-61 source capture and adds
an independent source-side owner map for every public continuum slot.  For
Type-49 candidates it records the literal Fortran ``xstarsetup.f90`` rank
coordinate

    eth = masterdata%rdat1(np1r) * 13.598

straight from the packed v0.6.47.2 master record.  It does *not* alter the
physical source run or ``calc_emis_all`` ranking; the corrected coordinate is
an oracle sidecar consumed by the patch-5.20.5.1 offline replay.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from . import v0472_heatt_zrems_running_sum_capture_v82_patch520 as base

RELEASE = "0.6.48.7.46.25.5.17.25.82-patch5.20.5.1"
SCHEMA = "xstar-tools-v82-patch52051-v0472-literal-type49-errc-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v82-patch52051-v0472-literal-type49-errc-oracle-v1"
VERIFY_NAME = "all61_literal_type49_errc_capture_verification.json"

# Extend the generated standalone probe without changing its physical source
# execution.  The owner map is built from source ``derived.npconi2`` plus the
# packed source record header/reals, so unselected rank candidates have an
# independent source identity as well.
_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    ' "consumer_selected","consumer_records","consumer_rate_types","consumer_data_types","consumer_ion_stages"\n]',
    ' "consumer_selected","consumer_records","consumer_rate_types","consumer_data_types","consumer_ion_stages",\n'
    ' "source_owner_record","source_owner_rate_type","source_owner_data_type",\n'
    ' "source_oracle_energy_ev","source_oracle_wavelength_angstrom","source_oracle_kind"\n]',
    1,
)
_PROBE = _PROBE.replace(
    '            rank_snapshot={\n'
    '              "epi":np.asarray(epi0,dtype=float).copy(),"active":active.copy(),\n'
    '              "wave":np.asarray(context.rrc_wavelength_angstrom,dtype=float).copy(),\n'
    '              "cemab":np.asarray(context.workspace.base.cemab,dtype=float).copy(),\n'
    '              "opakab":np.asarray(context.workspace.base.opakab,dtype=float).copy(),\n'
    '            }',
    '            active_set={int(x) for x in active if int(x)>0}\n'
    '            source_owner={}\n'
    '            for rec0 in range(1,int(getattr(context.master,"np2",0) or 0)+1):\n'
    '                slot0=int(context.derived.npconi2[rec0]) if rec0 < len(context.derived.npconi2) else 0\n'
    '                if slot0 not in active_set: continue\n'
    '                hdr0=context.master.header(rec0)\n'
    '                if int(getattr(hdr0,"rate_type",0)) != 7: continue\n'
    '                dt0=int(getattr(hdr0,"data_type",0))\n'
    '                raw0=context.master.record_reals(rec0)\n'
    '                source_owner[slot0]=(rec0,int(getattr(hdr0,"rate_type",0)),dt0,float(raw0[0]) if len(raw0)>0 else float("nan"))\n'
    '            rank_snapshot={\n'
    '              "epi":np.asarray(epi0,dtype=float).copy(),"active":active.copy(),\n'
    '              "wave":np.asarray(context.rrc_wavelength_angstrom,dtype=float).copy(),\n'
    '              "cemab":np.asarray(context.workspace.base.cemab,dtype=float).copy(),\n'
    '              "opakab":np.asarray(context.workspace.base.opakab,dtype=float).copy(),\n'
    '              "source_owner":source_owner,\n'
    '            }',
    1,
)
_PROBE = _PROBE.replace(
    '                cc=consumers.get(slot,[])\n'
    '                cem1=float(rank_snapshot["cemab"][0,slot]) if rank_snapshot["cemab"].ndim==2 and slot<rank_snapshot["cemab"].shape[1] else 0.0',
    '                cc=consumers.get(slot,[])\n'
    '                owner=rank_snapshot.get("source_owner",{}).get(slot)\n'
    '                owner_record=int(owner[0]) if owner is not None else 0\n'
    '                owner_rate=int(owner[1]) if owner is not None else 0\n'
    '                owner_dtype=int(owner[2]) if owner is not None else 0\n'
    '                owner_raw_first=float(owner[3]) if owner is not None else float("nan")\n'
    '                if owner_dtype==49 and math.isfinite(owner_raw_first):\n'
    '                    source_oracle_energy=max(0.1,owner_raw_first*13.598)\n'
    '                    source_oracle_kind="TYPE49_MASTERDATA_RDAT1_NP1R_X_13P598"\n'
    '                else:\n'
    '                    source_oracle_energy=energy\n'
    '                    source_oracle_kind="CAPTURED_GENERIC_RRC_COORDINATE"\n'
    '                source_oracle_wave=12398.4016/source_oracle_energy if source_oracle_energy>0.0 else 0.0\n'
    '                cem1=float(rank_snapshot["cemab"][0,slot]) if rank_snapshot["cemab"].ndim==2 and slot<rank_snapshot["cemab"].shape[1] else 0.0',
    1,
)
_PROBE = _PROBE.replace(
    '                  "consumer_data_types":";".join(str(int(getattr(x,"data_type",0))) for x in cc),\n'
    '                  "consumer_ion_stages":";".join(str(int(getattr(x,"ion_stage",0))) for x in cc),\n'
    '                })',
    '                  "consumer_data_types":";".join(str(int(getattr(x,"data_type",0))) for x in cc),\n'
    '                  "consumer_ion_stages":";".join(str(int(getattr(x,"ion_stage",0))) for x in cc),\n'
    '                  "source_owner_record":owner_record,"source_owner_rate_type":owner_rate,"source_owner_data_type":owner_dtype,\n'
    '                  "source_oracle_energy_ev":source_oracle_energy,"source_oracle_wavelength_angstrom":source_oracle_wave,\n'
    '                  "source_oracle_kind":source_oracle_kind,\n'
    '                })',
    1,
)

# Keep the historical generated-probe module name expected by base.capture.
_DRIVER = base._DRIVER


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    rank_path = bundle / base.RANK_INPUT_NAME
    rows = _read_csv(rank_path) if rank_path.is_file() else []
    call2 = [
        r for r in rows
        if int(r.get("dsec_call_id", "0") or 0) == 2
        and int(r.get("evaluation_index", "0") or 0) == 1
        and r.get("active_candidate", "1") not in ("0", "")
    ]
    type49 = [r for r in call2 if int(r.get("source_owner_data_type", "0") or 0) == 49]
    missing_owner = [r for r in call2 if int(r.get("source_owner_record", "0") or 0) <= 0]
    wrong_kind = [r for r in type49 if r.get("source_oracle_kind") != "TYPE49_MASTERDATA_RDAT1_NP1R_X_13P598"]
    bad_energy = []
    for r in type49:
        try:
            if not (float(r.get("source_oracle_energy_ev", "nan")) > 0.0):
                bad_energy.append(r)
        except Exception:
            bad_energy.append(r)
    if len(call2) != 1957:
        errors.append(f"call2_rank_rows={len(call2)}")
    if len(type49) != 797:
        errors.append(f"literal_type49_rows={len(type49)}")
    if len(missing_owner) != 105:
        errors.append(f"ownerless_source_candidate_rows={len(missing_owner)}")
    if wrong_kind:
        errors.append(f"wrong_type49_oracle_kind_rows={len(wrong_kind)}")
    if bad_energy:
        errors.append(f"bad_type49_oracle_energy_rows={len(bad_energy)}")
    result = {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
        "actual_v0472_runtime_capture": True,
        "physical_source_ranking_modified": False,
        "literal_type49_oracle_sidecar_only": True,
        "call2_rank_input_rows": len(call2),
        "literal_type49_rows": len(type49),
        "source_owner_rows": len(call2) - len(missing_owner),
        "ownerless_source_candidate_rows": len(missing_owner),
        "literal_type49_oracle_kind": "MASTERDATA_RDAT1_NP1R_X_13P598",
        "parent_absorption_verifier_required": False,
    }
    (bundle / VERIFY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    old_probe = base._PROBE
    old_driver = base._DRIVER
    try:
        base._PROBE = _PROBE
        base._DRIVER = _DRIVER
        base.capture(source_archive, atdb_path, output_dir, parameters_json, coheat_path)
    finally:
        base._PROBE = old_probe
        base._DRIVER = old_driver
    return verify(output_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("source_archive", type=Path)
    cap.add_argument("atdb_path", type=Path)
    cap.add_argument("output_dir", type=Path)
    cap.add_argument("parameters_json", type=Path)
    cap.add_argument("--coheat-path", type=Path)
    cap.add_argument("--output-json", type=Path)
    ver = sub.add_parser("verify")
    ver.add_argument("bundle", type=Path)
    ver.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path) \
            if args.command == "capture" else verify(args.bundle)
    except Exception as exc:
        result = {
            "schema": VERIFY_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
