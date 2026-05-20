from pathlib import Path

import pytest


def _write_minimal_fits_like_file(path: Path) -> None:
    # Lightweight resolver validation only checks a FITS SIMPLE card and a
    # minimum FITS block length; these tests do not need a real ATDB table.
    header = b"SIMPLE  =                    T"
    path.write_bytes(header + b" " * (2880 - len(header)))


def test_data_path_roundtrip(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    # Isolate this datapath round-trip test from the runtime precedence
    # of XSTAR_ATDB_FITS. In normal runtime use the environment variable
    # intentionally takes precedence over the saved datapath.
    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)
    monkeypatch.delenv("XSTAR_ATDB", raising=False)

    fake_pkg = tmp_path / "pkg"
    fake_pkg.mkdir()
    dp_file = fake_pkg / "datapath"
    monkeypatch.setattr(data, "DATAPATH_FILE", dp_file)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    atdb = data_dir / "atdb.fits"
    _write_minimal_fits_like_file(atdb)

    saved = data.set_data_path(atdb)
    assert saved == data_dir.resolve()
    assert data.get_data_path() == data_dir.resolve()
    assert data.find_atdb_file() == atdb.resolve()


def test_resolve_atdb_path_explicit_does_not_remember_parent_by_default(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)

    dp_file = tmp_path / "datapath"
    monkeypatch.setattr(data, "DATAPATH_FILE", dp_file)
    atdb = tmp_path / "atdb.fits"
    _write_minimal_fits_like_file(atdb)

    resolved = data.resolve_atdb_path(atdb, prompt=False)
    assert resolved == atdb.resolve()
    assert data.get_data_path() is None

    remembered = data.resolve_atdb_path(atdb, prompt=False, remember_explicit=True)
    assert remembered == atdb.resolve()
    assert data.get_data_path() == tmp_path.resolve()


def test_download_data_decline_and_set_existing_path(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)

    dp_file = tmp_path / "datapath"
    monkeypatch.setattr(data, "DATAPATH_FILE", dp_file)
    monkeypatch.setattr(data, "_remote_file_size", lambda url: 1234)
    atdb = tmp_path / "existing" / "atdb.fits"
    atdb.parent.mkdir()
    _write_minimal_fits_like_file(atdb)
    answers = iter(["n", str(atdb)])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    resolved = data.download_data(prompt=True)
    assert resolved == atdb.resolve()
    assert data.get_data_path() == atdb.parent.resolve()


def test_find_atdb_file_honors_short_xstar_atdb_env(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)
    dp_file = tmp_path / "datapath"
    monkeypatch.setattr(data, "DATAPATH_FILE", dp_file)
    atdb = tmp_path / "atdb.fits"
    _write_minimal_fits_like_file(atdb)
    monkeypatch.setenv("XSTAR_ATDB", str(atdb))

    assert data.find_atdb_file(remember=False) == atdb.resolve()
    assert data.resolve_atdb_path(None, prompt=False) == atdb.resolve()


def test_resolve_atdb_path_blank_explicit_falls_back_to_env(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)
    dp_file = tmp_path / "datapath"
    monkeypatch.setattr(data, "DATAPATH_FILE", dp_file)
    atdb = tmp_path / "atdb.fits"
    _write_minimal_fits_like_file(atdb)
    monkeypatch.setenv("XSTAR_ATDB", str(atdb))

    assert data.resolve_atdb_path("", prompt=False) == atdb.resolve()


def test_find_atdb_file_uses_datapath_when_env_unset(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)
    monkeypatch.delenv("XSTAR_ATDB", raising=False)

    dp_file = tmp_path / "datapath"
    monkeypatch.setattr(data, "DATAPATH_FILE", dp_file)
    monkeypatch.setattr(data, "_candidate_datapath_files", lambda: [dp_file])

    data_dir = tmp_path / "xstar_data"
    data_dir.mkdir()
    atdb = data_dir / "atdb.fits"
    _write_minimal_fits_like_file(atdb)
    dp_file.write_text(str(data_dir) + "\n", encoding="utf-8")

    assert data.get_data_path() == data_dir.resolve()
    assert data.find_atdb_file(remember=False) == atdb.resolve()
    assert data.resolve_atdb_path(None, prompt=False) == atdb.resolve()


def test_find_atdb_file_skips_stale_datapath_and_uses_next_candidate(tmp_path, monkeypatch):
    pytest.importorskip("astropy")
    import xstar_atomic.data as data

    monkeypatch.delenv("XSTAR_ATDB_FITS", raising=False)
    monkeypatch.delenv("XSTAR_ATDB", raising=False)

    stale_file = tmp_path / "stale_datapath"
    good_file = tmp_path / "good_datapath"
    stale_file.write_text(str(tmp_path / "missing_data") + "\n", encoding="utf-8")

    data_dir = tmp_path / "real_data"
    data_dir.mkdir()
    atdb = data_dir / "atdb.fits"
    _write_minimal_fits_like_file(atdb)
    good_file.write_text(str(data_dir) + "\n", encoding="utf-8")

    monkeypatch.setattr(data, "_candidate_datapath_files", lambda: [stale_file, good_file])
    assert data.get_data_paths() == [(tmp_path / "missing_data").resolve(), data_dir.resolve()]
    assert data.find_atdb_file(remember=False) == atdb.resolve()
