from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src" / "xstar_tools" / "xstar" / "cpp"


def test_manual_abundance_defaults_are_preserved():
    contract = (CPP / "xstar_parameter_contract.hpp").read_text()
    standalone = (CPP / "xstar_standalone.cpp").read_text()
    assert '{"mnabund", ParameterKind::Real, "1.0"' in contract
    assert 'add_real("mnabund", 1.0);' in standalone


def test_type49_lowering_honors_source_early_exit_before_curve_requirement():
    source = (CPP / "xstar_atdb_runtime.cpp").read_text()
    branch = source[source.index("else if (dt==49 || dt==53)") :]
    branch = branch[: branch.index("else if (!kLegacyActiveTypes.count(dt)")]

    assert "source_type49_skip" in branch
    assert "id1<=0 || id1>=b.nlev || h.nreal<=0" in branch
    assert "XSTAR_FIXED_OPCODE_SOURCE_SKIPPED" in branch
    assert branch.index("source_type49_skip") < branch.index("if(rr.size()<4)")


def test_source_skipped_opcode_is_zero_contribution():
    header = (CPP / "xstar_local_zone_engine.h").read_text()
    engine = (CPP / "local_zone_engine.cpp").read_text()
    assert "XSTAR_FIXED_OPCODE_SOURCE_SKIPPED = 201" in header
    assert "case XSTAR_FIXED_OPCODE_SOURCE_SKIPPED" in engine
    case = engine[engine.index("case XSTAR_FIXED_OPCODE_SOURCE_SKIPPED") :]
    case = case[: case.index("case XSTAR_FIXED_OPCODE_SIMPLE_UCALC")]
    assert "out.matrix_enabled = false" in case
    assert "c.lower_row = 0" in case
    assert "c.upper_row = 0" in case
