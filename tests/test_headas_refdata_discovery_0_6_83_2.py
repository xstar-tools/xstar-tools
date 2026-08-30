from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_headas_refdata_is_between_xstar_data_and_xstar_home():
    text = (CPP / "xstar_atdb_runtime.cpp").read_text()
    ax = text.index('std::getenv("XSTAR_DATA")', text.index("r.atdb_candidates"))
    ah = text.index('std::getenv("HEADAS")', ax)
    ao = text.index('std::getenv("XSTAR_HOME")', ah)
    cx = text.index('std::getenv("XSTAR_DATA")', text.index("r.coheat_candidates"))
    ch = text.index('std::getenv("HEADAS")', cx)
    co = text.index('std::getenv("XSTAR_HOME")', ch)
    assert ax < ah < ao
    assert cx < ch < co


def test_headas_refdata_paths_are_canonical_heasoft_locations():
    text = (CPP / "xstar_atdb_runtime.cpp").read_text()
    assert 'std::filesystem::path(v) / "refdata" / "atdb.fits"' in text
    assert 'std::filesystem::path(v) / "refdata" / "coheat.dat"' in text


def test_xstinitable_does_not_discover_headas():
    text = (CPP / "xstar_xspec_initable.cpp").read_text() + (CPP / "xstar_xspec_initable_cli.cpp").read_text()
    assert "HEADAS" not in text
