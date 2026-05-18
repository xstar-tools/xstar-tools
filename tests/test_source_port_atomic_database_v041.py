from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits

from xstar_atomic.source_port import (
    AtomicDatabaseError,
    DBWK2Instruction,
    UnportedXSTARRoutine,
    XSTARPythonDriver,
    XSTARStage,
    dbwk2,
    load_atomic_database_state,
    readtbl,
    register_atomic_database_stages,
    setptrs,
)


def _write_vector_hdu(name: str, values: np.ndarray, code: str) -> fits.BinTableHDU:
    values = np.asarray(values)
    column = fits.Column(name="DATA", format=f"{len(values)}{code}", array=[values])
    hdu = fits.BinTableHDU.from_columns([column], name=name)
    hdu.header["LENGTH"] = len(values)
    return hdu


def _write_mini_atdb(path: Path) -> list[dict]:
    # Ordered exactly as setptrs expects: element -> ion -> levels -> rate groups.
    records = [
        dict(dt=13, rt=11, reals=[1.0, 1.0], ints=[1, 1], chars=b"H"),
        dict(dt=14, rt=12, reals=[13.6], ints=[1, 1], chars=b"H I"),
        dict(dt=6, rt=13, reals=[0.0], ints=[1, 101], chars=b"1s"),
        dict(dt=6, rt=13, reals=[10.2], ints=[2, 102], chars=b"2p"),
        dict(dt=53, rt=7, reals=[13.6], ints=[1, 201], chars=b"pi1"),
        dict(dt=1, rt=1, reals=[3.4], ints=[2, 202], chars=b"pi2"),
        dict(dt=50, rt=4, reals=[-1215.67, 1.0], ints=[2, 1, 1], chars=b"lya"),
        dict(dt=11, rt=9, reals=[2431.0], ints=[2, 1], chars=b"2ph"),
        dict(dt=71, rt=14, reals=[1025.0], ints=[2, 1], chars=b"sup"),
        dict(dt=1, rt=6, reals=[1.0], ints=[1], chars=b"rr"),
        dict(dt=7, rt=8, reals=[1.0], ints=[1], chars=b"dr"),
        dict(dt=51, rt=3, reals=[1.0], ints=[2, 1], chars=b"ce"),
        dict(dt=57, rt=5, reals=[1.0], ints=[1], chars=b"bf"),
        dict(dt=99, rt=40, reals=[1.0], ints=[1], chars=b"ci"),
        dict(dt=2, rt=2, reals=[1.0], ints=[1], chars=b"cx"),
        dict(dt=14, rt=12, reals=[0.0], ints=[2, 2], chars=b"H II"),
        dict(dt=6, rt=13, reals=[0.0], ints=[1, 103], chars=b"bare"),
        dict(dt=50, rt=4, reals=[100.0], ints=[1, 1], chars=b"line"),
        dict(dt=13, rt=11, reals=[0.1, 4.0], ints=[2, 2], chars=b"He"),
        dict(dt=14, rt=12, reals=[24.6], ints=[1, 3], chars=b"He I"),
        dict(dt=6, rt=13, reals=[0.0], ints=[1, 104], chars=b"1s2"),
        dict(dt=53, rt=7, reals=[24.6], ints=[1, 203], chars=b"hepi"),
        dict(dt=0, rt=0, reals=[], ints=[], chars=b""),
    ]

    pointer_rows = []
    reals: list[float] = []
    integers: list[int] = []
    chars: list[int] = []
    for recno, rec in enumerate(records, start=1):
        rp = len(reals) + 1
        ip = len(integers) + 1
        kp = len(chars) + 1
        reals.extend(rec["reals"])
        integers.extend(rec["ints"])
        chars.extend(rec["chars"])
        pointer_rows.append(
            [
                recno,
                rec["dt"],
                rec["rt"],
                0,
                len(rec["reals"]),
                len(rec["ints"]),
                len(rec["chars"]),
                rp,
                ip,
                kp,
            ]
        )

    primary = fits.PrimaryHDU()
    primary.header["DATE"] = "2026-06-17"
    primary.header["CREATOR"] = "pytest-mini-atdb"
    hdul = fits.HDUList(
        [
            primary,
            _write_vector_hdu("POINTERS", np.asarray(pointer_rows, dtype=np.int32).reshape(-1), "J"),
            _write_vector_hdu("REALS", np.asarray(reals, dtype=np.float32), "E"),
            _write_vector_hdu("INTEGERS", np.asarray(integers, dtype=np.int32), "J"),
            _write_vector_hdu("CHARS", np.asarray(chars, dtype=np.uint8), "B"),
        ]
    )
    # POINTERS LENGTH is records, unlike the vector length.
    hdul["POINTERS"].header["LENGTH"] = len(records)
    hdul.writeto(path)
    return records


def test_readtbl_loads_packed_vectors_without_changing_fortran_indices(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    records = _write_mini_atdb(atdb)
    master = readtbl(atdb)
    try:
        assert master.np2 == len(records)
        assert master.creation_date == "2026-06-17"
        assert master.creator == "pytest-mini-atdb"
        h = master.header(7)
        assert (h.data_type, h.rate_type, h.real_ptr) == (50, 4, 8)
        assert master.record_reals(7)[0] == pytest.approx(-1215.67, rel=1e-6)
        assert master.record_integers(7).tolist() == [2, 1, 1]
        assert master.record_chars(7) == b"lya"
        assert master.local_level_index(5) == 1
    finally:
        master.close()


def test_setptrs_reproduces_parent_rate_line_continuum_and_level_pointers(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    master = readtbl(atdb)
    try:
        p = setptrs(master, llinabs=True)
        assert (p.n_elements, p.n_ions, p.n_level_records) == (2, 3, 4)
        assert (p.nlsvn, p.ncsvn) == (4, 3)

        # Element and ion chains.
        assert p.npfirst[11] == 1
        assert p.npnxt[1] == 19
        assert p.npfirst[12] == 2
        assert (p.npnxt[2], p.npnxt[16]) == (16, 20)
        assert p.npar[2] == 1
        assert p.npar[16] == 1
        assert p.npar[20] == 19

        # Level chains and source-compatible global/local level maps.
        assert p.npfirst[13] == 3
        assert (p.npnxt[3], p.npnxt[4], p.npnxt[17]) == (4, 17, 21)
        assert p.npfi[13, 1] == 3
        assert p.npfi[13, 2] == 17
        assert p.npfi[13, 3] == 21
        assert p.nlevs[1:4].tolist() == [2, 1, 1]
        assert p.npilev[1, 1] == 1
        assert p.npilev[2, 1] == 2
        assert p.npilev[1, 2] == 3
        assert p.npilev[1, 3] == 4
        assert p.npilevi[1:5].tolist() == [1, 2, 1, 1]
        assert p.level_record_by_global_index[1:5].tolist() == [3, 4, 17, 21]

        # Lines and continua round trip exactly.
        assert p.nplin[1:].tolist() == [7, 8, 9, 18]
        assert [p.nplini[x] for x in (7, 8, 9, 18)] == [1, 2, 3, 4]
        assert p.npcon[1:].tolist() == [5, 6, 22]
        assert [p.npconi2[x] for x in (5, 6, 22)] == [1, 2, 3]
        assert (p.npconi[3], p.npconi[4], p.npconi[21]) == (1, 2, 3)

        # Rate-family chains span ion blocks.
        assert p.npfirst[4] == 7
        assert p.npnxt[7] == 18
        assert p.npfi[4, 1] == 7
        assert p.npfi[4, 2] == 18
        assert p.npfirst[7] == 5
        assert p.npnxt[5] == 22
        assert p.npfi[2, 1] == 15

        # llinabs uses a sparse source-array override rather than copying REALS.
        assert master.record_reals(7)[0] == pytest.approx(1215.67, rel=1e-6)
        assert len(master.rdat1.overrides) == 1
    finally:
        master.close()


def test_load_atomic_database_state_and_driver_complete_first_three_stages(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)

    result = load_atomic_database_state(atdb)
    try:
        assert result.atomic_state.master is result.master
        assert result.atomic_state.derived is result.derived
        assert result.atomic_state.provenance["pointer_initialization_ready"] is True
        assert result.atomic_state.provenance["n_ions"] == 3
    finally:
        result.atomic_state.close()

    driver = XSTARPythonDriver()
    register_atomic_database_stages(driver, atdb_path=atdb)
    with pytest.raises(UnportedXSTARRoutine) as exc:
        driver.run()
    assert exc.value.stage is XSTARStage.INITIALIZE_RADIATION
    assert exc.value.state is not None
    exc.value.state.atomic.close()

    state = driver.run(stop_after=XSTARStage.BUILD_POINTERS)
    try:
        assert state.provenance["completed_stages"] == [
            "setup",
            "read_atomic_database",
            "build_pointers",
        ]
        assert state.atomic.derived.n_ions == 3
    finally:
        state.atomic.close()


def test_dbwk2_runtime_operations_use_translated_pointer_state(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    master = readtbl(atdb)
    try:
        built = dbwk2(DBWK2Instruction.BUILD_POINTERS, master).payload
        inventory = dbwk2(DBWK2Instruction.RECORD_INVENTORY, master, derived=built).payload
        counts = dbwk2(DBWK2Instruction.RECORDS_PER_ION, master, derived=built).payload
        report = dbwk2(DBWK2Instruction.POINTER_REPORT, master, derived=built).payload
        assert len(inventory) == master.np2
        assert len(counts) == 3
        assert counts[0]["n_levels"] == 2
        assert report["npfirst"][11] == 1
        with pytest.raises(NotImplementedError):
            dbwk2(3, master, derived=built)
    finally:
        master.close()


def test_setptrs_rejects_continuum_record_for_missing_level(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    with fits.open(atdb, mode="update") as hdul:
        ints = hdul["INTEGERS"].data["DATA"][0]
        # Record 5 starts after element(2)+ion(2)+two levels(4) = index 8.
        ints[8] = 99
        hdul.flush()
    master = readtbl(atdb)
    try:
        with pytest.raises(AtomicDatabaseError, match="missing local level 99"):
            setptrs(master)
    finally:
        master.close()


def test_pointer_cache_roundtrip_and_stale_detection(tmp_path: Path):
    from xstar_atomic.source_port import (
        load_derived_pointer_cache,
        save_derived_pointer_cache,
        write_atomic_database_products,
    )

    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    master = readtbl(atdb)
    try:
        derived = setptrs(master)
        cache = save_derived_pointer_cache(master, derived, tmp_path / "pointers.npz")
        loaded = load_derived_pointer_cache(master, cache)
        assert loaded.npfirst.tolist() == derived.npfirst.tolist()
        assert loaded.npfi.tolist() == derived.npfi.tolist()
        outputs = write_atomic_database_products(master, loaded, tmp_path / "products")
        assert Path(outputs["pointer_cache"]).is_file()
        assert Path(outputs["json"]).is_file()
    finally:
        master.close()

    # Rewriting the FITS file changes the fingerprint and invalidates the cache.
    with fits.open(atdb, mode="update") as hdul:
        hdul[0].header["CREATOR"] = "changed"
        hdul.flush()
    master2 = readtbl(atdb)
    try:
        with pytest.raises(AtomicDatabaseError, match="stale pointer cache"):
            load_derived_pointer_cache(master2, cache)
    finally:
        master2.close()


def test_atomic_database_cli_writes_reusable_products(tmp_path: Path, capsys):
    from xstar_atomic.source_port_atomic_db_cli import main

    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    out_dir = tmp_path / "out"
    rc = main(
        [
            "--atdb",
            str(atdb),
            "--out-dir",
            str(out_dir),
            "--print-summary",
        ]
    )
    assert rc == 0
    text = capsys.readouterr().out
    assert "atomic_database_runtime_subsystem_ready=True" in text
    assert (out_dir / "xstar_atomic_derived_pointers.npz").is_file()
    assert (out_dir / "xstar_atomic_database_port_summary.json").is_file()
    assert (out_dir / "xstar_atomic_ions.csv").is_file()


def test_atomic_database_source_port_api_is_public():
    import xstar_atomic as xa

    assert xa.__version__ == "0.4.18"
    assert xa.readtbl is readtbl
    assert callable(xa.load_atomic_database_state)
    assert "readtbl" in xa.__all__
