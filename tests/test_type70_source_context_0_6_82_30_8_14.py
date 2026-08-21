from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_cpp_type70_uses_canonical_final_level_integer_slot():
    text = (_root() / 'src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp').read_text()
    start = text.index('case 70: {')
    end = text.index('case 75:', start)
    block = text[start:end]
    assert 'ii[ii.size()-4]' in block
    assert 'b.nlev+ii[ii.size()-3]-1' not in block
    assert 'final *level*' in block


def test_python_type70_lowerers_use_canonical_final_level_integer_slot():
    native = (_root() / 'src/xstar_tools/xstar/native_fixed_program.py').read_text()
    start = native.index('elif dt == 70:')
    end = native.index('elif dt == 75:', start)
    block = native[start:end]
    assert 'raw_ints[-4]' in block
    assert 'raw_ints[-3]) - 1' not in block

    ucalc = (_root() / 'src/xstar_tools/xstar/ucalc.py').read_text()
    start = ucalc.index('def _eval_type70')
    end = ucalc.index('def _eval_type81', start)
    block = ucalc[start:end]
    assert 'r.integers[-4]' in block
    assert 'r.integers[-3])-1' not in block


def test_cpp_type70_uses_next_ion_type13_context_and_phint53hunt():
    text = (_root() / 'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    start = text.index('case 70:{')
    end = text.index('case 92:{', start)
    block = text[start:end]
    assert 'source_final_level' in block
    assert 'std::min(raw_source_bound_local, current_nlev - 1)' in block
    assert 'level.ion_stage == record.ion_stage + 1' in block
    assert 'source_destination->energy_ev' in block
    assert 'source_destination->statistical_weight' in block
    assert 'std::abs(bound_energy + destination_energy)' in block
    assert 'evaluate_type99_phint53hunt' in block
    assert 'evaluate_type53_source_integral' not in block
    assert 'c.ans1 = ph.pirt * scale;' in block
    assert 'c.ans2 = cal.rec * cf_ne;' in block
    assert 'c.ans3 = -ph.rrcl;' in block
    assert 'c.ans4 = -ph.piht * scale;' in block
    assert 'c.ans5 = -ph.rrcl2;' in block
    assert 'c.ans6 = -ph.piht2 * scale;' in block


def test_cpp_type70_retains_source_global_hydrogen_density_gate():
    text = (_root() / 'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    start = text.index('case 70:{')
    end = text.index('case 92:{', start)
    block = text[start:end]
    assert 'source_global_hydrogen_ion' in block
    assert 'density=std::min(density,1e8)' in block
    assert 'record.ion_index==1' not in block
    assert 'record.ion_index == 1' not in block
