from __future__ import annotations

from pathlib import Path

import numpy as np

from xstar_atomic.source_port import (
    FortranPackedVector,
    default_derived_pointer_cache_path,
    load_atomic_database_state,
)
from xstar_atomic.source_port import physical_runner as runner
import importlib.util

_HELPER_PATH = Path(__file__).with_name("test_source_port_atomic_database_v041.py")
_HELPER_SPEC = importlib.util.spec_from_file_location(
    "xstar_atomic_test_source_port_atomic_database_v041", _HELPER_PATH
)
assert _HELPER_SPEC is not None and _HELPER_SPEC.loader is not None
_HELPER_MODULE = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(_HELPER_MODULE)
_write_mini_atdb = _HELPER_MODULE._write_mini_atdb


def test_v0473_sparse_slice_uses_sorted_vectorized_override_ranges():
    base = np.arange(100_000, dtype=np.float64)
    vector = FortranPackedVector(base, name="test")
    indices = np.arange(1, 20_001, 2, dtype=np.int64)
    values = -indices.astype(np.float64)
    vector.set_overrides(indices, values)

    # A non-overlapping slice remains a direct view even though many overrides exist.
    untouched = vector.slice(50_001, 8)
    assert np.shares_memory(untouched, base)
    assert untouched.tolist() == base[50_000:50_008].tolist()

    # Intersecting slices and arbitrary gathers receive exactly the sparse overlay.
    changed = vector.slice(9, 7)
    expected = base[8:15].copy()
    for one_based in range(9, 16):
        if one_based % 2 == 1:
            expected[one_based - 9] = -float(one_based)
    assert np.array_equal(changed, expected)
    gathered = vector.gather(np.asarray([1, 2, 3, 20_000, 50_001]))
    assert gathered.tolist() == [-1.0, 1.0, -3.0, 19_999.0, 50_000.0]


def test_v0473_default_pointer_cache_is_atdb_specific(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    expected = tmp_path / "atdb.fits.xstar_atomic_source_port.npz"
    assert default_derived_pointer_cache_path(atdb) == expected


def test_v0473_pointer_cache_miss_then_hit(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    cache = default_derived_pointer_cache_path(atdb)

    first = load_atomic_database_state(
        atdb,
        llinabs=True,
        pointer_cache=cache,
        use_pointer_cache=True,
    )
    try:
        assert first.derived.provenance["pointer_cache_status"] == "miss"
        assert cache.is_file()
    finally:
        first.atomic_state.close()

    second = load_atomic_database_state(
        atdb,
        llinabs=True,
        pointer_cache=cache,
        use_pointer_cache=True,
    )
    try:
        assert second.derived.provenance["pointer_cache_status"] == "hit"
        assert second.master.record_reals(7)[0] > 0.0
    finally:
        second.atomic_state.close()


def test_v0473_vectorized_metadata_builder_and_npz_roundtrip(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    built = load_atomic_database_state(atdb, llinabs=True)
    try:
        # The new builder reads scalar packed fields with vector gathers and no
        # longer allocates full real/integer record slices for each metadata row.
        built.master.record_reals = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("record_reals must not be used by vectorized metadata")
        )
        built.master.record_integers = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("record_integers must not be used by vectorized metadata")
        )
        metadata = runner.build_source_output_metadata(built.master, built.derived)
        assert (len(metadata.levels), len(metadata.lines), len(metadata.rrcs)) == (4, 4, 3)
        assert metadata.lines[0].wavelength_angstrom > 0.0

        cache = runner.default_output_metadata_cache_path(atdb)
        runner.save_source_output_metadata_cache(built.master, metadata, cache)
        loaded = runner.load_source_output_metadata_cache(built.master, cache)
        assert loaded.levels == metadata.levels
        assert loaded.lines == metadata.lines
        assert loaded.rrcs == metadata.rrcs
        assert loaded.provenance["metadata_cache_status"] == "hit"
    finally:
        built.atomic_state.close()


def test_v0473_prepare_cache_reports_miss_then_hit(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    cache_dir = tmp_path / "cache"
    events: list[str] = []

    first = runner.prepare_xstar_python_cache(
        atdb_path=atdb,
        cache_dir=cache_dir,
        progress_callback=lambda event, details: events.append(event),
    )
    assert first.ready is True
    assert first.pointer_cache_status == "miss"
    assert first.metadata_cache_status == "miss_written"
    assert first.pointer_cache_path.is_file()
    assert first.metadata_cache_path.is_file()
    assert events[0] == "cache_prepare_start"
    assert events[-1] == "cache_prepare_done"

    second = runner.prepare_xstar_python_cache(atdb_path=atdb, cache_dir=cache_dir)
    assert second.ready is True
    assert second.pointer_cache_status == "hit"
    assert second.metadata_cache_status == "hit"


def test_v0473_live_radiation_accepts_bremsmap_tail_and_inactive_capacity():
    from types import SimpleNamespace

    from xstar_atomic.source_port.ucalc import _radiation_arrays

    state = SimpleNamespace(
        epim_eV=np.asarray([1.0, 2.0, 4.0, 8.0]),
        bremsam=np.asarray([10.0, 20.0, 30.0, 40.0, 999.0]),
        bremsint=np.asarray([4.0, 3.0, 2.0, 1.0, 1234.0, 5678.0]),
    )
    epi, brem, bint = _radiation_arrays(state)
    assert epi.tolist() == [1.0, 2.0, 4.0, 8.0]
    assert brem.tolist() == [10.0, 20.0, 30.0, 40.0]
    assert bint.tolist() == [4.0, 3.0, 2.0, 1.0]


def test_v0473_live_radiation_rejects_short_active_arrays():
    from types import SimpleNamespace

    import pytest

    from xstar_atomic.source_port.ucalc import _radiation_arrays

    state = SimpleNamespace(
        epim_eV=np.asarray([1.0, 2.0, 4.0, 8.0]),
        bremsam=np.asarray([10.0, 20.0, 30.0]),
        bremsint=np.asarray([4.0, 3.0, 2.0, 1.0, 0.0]),
    )
    with pytest.raises(ValueError, match="invalid live radiation arrays"):
        _radiation_arrays(state)


def test_v0474_source_brems_arrays_keep_full_high_resolution_capacity(tmp_path: Path):
    """The shared XSTAR arrays must satisfy both trnfrc and reduced-grid ucalc."""
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    parameters = runner.normalize_xstar_parameters(
        {
            "ncn2": 1200,
            "nsteps": 1,
            "npass": 1,
            "spectrum": "pow",
            "abundtbl": "xdef",
        }
    )
    state, built = runner._build_initial_state(
        parameters,
        atdb_path=atdb,
        use_cache=False,
    )
    try:
        assert state.control["ncn2"] == 1200
        assert state.control["ncn2m"] == 999
        assert np.asarray(state.radiation.bremsa).size == 1200
        assert np.asarray(state.radiation.bremsam).size == 1200
        assert np.asarray(state.radiation.bremsint).size == 1200
    finally:
        built.atomic_state.close()


def test_v0474_trnfrc_accepts_the_full_capacity_shared_bremsint():
    from xstar_atomic.source_port.radial_transfer import trnfrc

    n = 12
    epi = np.geomspace(0.1, 1.0e4, n)
    result = trnfrc(
        direction=-1,
        radius_cm=1.0e18,
        column_limit_cm2=1.0e20,
        hydrogen_density_cm3=1.0,
        epi_eV=epi,
        zremsz=np.ones(n),
        dpthc=np.zeros((2, n)),
        opakc=np.ones(n),
        zrems=np.ones((5, n)),
        bremsa_before=np.zeros(n),
        bremsint_before=np.zeros(n),
        ncn2=n,
    )
    assert result.bremsint_after.size == n
    assert np.all(np.isfinite(result.bremsint_after))
