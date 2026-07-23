from __future__ import annotations
import sys, tempfile, types
from pathlib import Path


def _runner():
    try:
        import astropy.io.fits  # type: ignore  # noqa: F401
    except Exception:
        astropy=types.ModuleType('astropy'); io=types.ModuleType('astropy.io'); fits=types.ModuleType('astropy.io.fits')
        io.fits=fits; astropy.io=io
        sys.modules.setdefault('astropy',astropy); sys.modules.setdefault('astropy.io',io); sys.modules.setdefault('astropy.io.fits',fits)
    import xstar_tools.xstar.physical_runner as pr
    return pr


def test_rrc_output_metadata_cache_roundtrip_retains_literal_type49_rank_identity():
    pr=_runner()
    from xstar_tools.xstar.output_writers import RRCOutputMetadata, SourceOutputMetadata
    old=pr.atomic_database_fingerprint; pr.atomic_database_fingerprint=lambda master:'fixture'
    try:
        md=SourceOutputMetadata(rrcs=(RRCOutputMetadata(17,31,123.456,'mg_xi','fixture',
            source_record=987654321,data_type=49,rank_threshold_eV=77.125),))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'m.npz'; pr.save_source_output_metadata_cache(object(),md,p)
            row=pr.load_source_output_metadata_cache(object(),p).rrcs[0]
        assert pr.OUTPUT_METADATA_CACHE_FORMAT_VERSION == 9
        assert row.source_record == 987654321
        assert row.data_type == 49
        assert row.rank_threshold_eV == 77.125
    finally:
        pr.atomic_database_fingerprint=old


def test_cpp_rrc_path_consumes_live_continuum_tau_without_merging_dual_curve_owners():
    root=Path(__file__).resolve().parents[1]
    fixed=(root/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'NativeBoundFreeCurve opacity_curve;' in fixed
    assert 'NativeBoundFreeCurve emission_curve;' in fixed
    assert 'const bool live_tau_available = continuum_index > 0' in fixed
    assert '2.0 * pescv_source(tau1 + tau2) * covering' in fixed
