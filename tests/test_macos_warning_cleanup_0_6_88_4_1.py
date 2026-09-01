from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_apple_warning_helper_is_scoped():
    text = (CPP / "xstar_compiler_warnings.hpp").read_text()
    assert "defined(__APPLE__) && defined(__clang__)" in text
    assert "XSTAR_APPLE_MAYBE_UNUSED [[maybe_unused]]" in text
    assert '-Wdeprecated-declarations' in text


def test_no_global_warning_suppression_added():
    makefile = (CPP / "Makefile").read_text()
    for token in ("-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-const-variable", "-Wno-deprecated-declarations"):
        assert token not in makefile


def test_level_population_warning_target_annotated():
    text = (CPP / "level_population.cpp").read_text()
    assert "XSTAR_APPLE_MAYBE_UNUSED inline const double& M(" in text


def test_opacity_warning_targets_annotated():
    text = (CPP / "opacity_kernels.cpp").read_text()
    for token in (
        "XSTAR_APPLE_MAYBE_UNUSED static inline void voigte_small_a_farwing4(",
        "XSTAR_APPLE_MAYBE_UNUSED static inline void type50_consume_full(",
        "XSTAR_APPLE_MAYBE_UNUSED static std::pair<int,int> small_a_core_bounds_localized_v0682382(",
        "XSTAR_APPLE_MAYBE_UNUSED const bool production_inline_avx2_v064812328",
        "XSTAR_APPLE_MAYBE_UNUSED static const bool decompose_v064812328",
        "XSTAR_APPLE_MAYBE_UNUSED static const bool force_12330_hint_consume_v064812331",
        "XSTAR_APPLE_MAYBE_UNUSED static const bool decompose_cursor_v064812331",
        "XSTAR_APPLE_MAYBE_UNUSED static const bool enable_tmpop_prep_v064812332",
        "XSTAR_APPLE_MAYBE_UNUSED static const bool enable_tmpe_prep_v064812332",
    ):
        assert token in text


def test_publication_and_runtime_constants_annotated():
    files = {
        "xstar_science_fits.cpp": ("kErgPerEv", "kFourPi", "kOraclePublicRrcSegments"),
        "xstar_standalone.cpp": ("source_brems_kev_per_t7_v068228", "kV82PublicLineInventory"),
        "xstar_atdb_runtime.cpp": ("kProgramAbi", "kType53LayoutMagic", "kType49LayoutMagic", "kType99LayoutMagic"),
    }
    for name, symbols in files.items():
        text = (CPP / name).read_text()
        for symbol in symbols:
            lines = [line for line in text.splitlines() if symbol in line and not line.lstrip().startswith("//")]
            assert lines and any("XSTAR_APPLE_MAYBE_UNUSED" in line for line in lines), (name, symbol)


def test_shared_ptr_expression_preserved_off_apple():
    text = (CPP / "local_zone_engine.cpp").read_text()
    assert "#if defined(__APPLE__) && defined(__clang__)" in text
    assert "XSTAR_APPLE_CLANG_IGNORE_DEPRECATED_DECLARATIONS" in text
    assert "} else if (!bound_free_payload_v06823087.unique()) {" in text


def test_version_metadata():
    assert 'version = "0.6.88.4.1"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.88.4.1" in (CPP / "Makefile").read_text()
