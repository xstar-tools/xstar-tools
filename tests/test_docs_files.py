from pathlib import Path
import re


def test_user_guides_and_sphinx_scaffold_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "user_guide.md").is_file()
    assert (root / "docs" / "user_guide.tex").is_file()
    assert (root / "docs" / "sphinx" / "source" / "conf.py").is_file()
    assert (root / "docs" / "sphinx" / "source" / "api.rst").is_file()
    assert (root / "examples" / "06_high_level_api_quickstart.py").is_file()
    assert (root / "examples" / "README.md").is_file()


def test_examples_readme_has_bash_command_for_each_example():
    root = Path(__file__).resolve().parents[1]
    examples_dir = root / "examples"
    readme = (examples_dir / "README.md").read_text()
    example_names = sorted(path.name for path in examples_dir.glob("*.py"))

    assert example_names, "No example scripts found"
    bash_blocks = re.findall(r"```bash\n(.*?)\n```", readme, flags=re.DOTALL)
    joined_blocks = "\n".join(bash_blocks)

    missing_sections = [name for name in example_names if f"### `{name}`" not in readme]
    missing_commands = [name for name in example_names if f"examples/{name}" not in joined_blocks]

    assert not missing_sections
    assert not missing_commands



def test_public_api_documentation_is_consistent_across_guides():
    root = Path(__file__).resolve().parents[1]
    md = (root / "docs" / "user_guide.md").read_text(encoding="utf-8")
    tex = (root / "docs" / "user_guide.tex").read_text(encoding="utf-8")
    rst_user = (root / "docs" / "sphinx" / "source" / "user_guide.rst").read_text(encoding="utf-8")
    rst_api = (root / "docs" / "sphinx" / "source" / "api.rst").read_text(encoding="utf-8")

    required_plain = [
        "open_database",
        "get_levels",
        "get_lines",
        "get_wavelengths",
        "get_energies",
        "match_line",
        "match_lines",
        "get_collisions",
        "get_photoionization",
        "get_recombination",
        "calc_emissivity",
        "LocalPlasmaState",
        "RadiationField",
        "EscapeContext",
        "context_from_values",
        "context_from_xstar_run",
        "RateEvaluation",
        "evaluate_type50_bound_bound",
        "calc_rate",
        "calc_triplet",
        "solve_populations",
        "build_matrix",
        "db.context.from_values",
        "db.context.from_xstar_run",
        "db.rates.type50",
        "db.audit.type50_line_pumping",
        "db.validate.compare_xstar_run",
        "db.solve.ion",
        "db.matrix.build_ion",
        "type50_bound_bound",
    ]
    for token in required_plain:
        assert token in md, token
        assert token in rst_user, token

    # LaTeX guide contains some names in prose (escaped underscores) and many
    # names in lstlisting blocks (raw underscores), so accept either spelling.
    for token in required_plain:
        escaped = token.replace("_", "\\_")
        assert token in tex or escaped in tex, token

    for module_name in [
        "xstar_atomic.workflow",
        "xstar_atomic.rates",
        "xstar_atomic.matrix",
        "xstar_atomic.solve",
        "xstar_atomic.validate",
        "xstar_atomic.runs",
        "xstar_atomic.context",
        "xstar_atomic.rates_type50",
        "xstar_atomic.audit",
    ]:
        assert module_name in rst_api, module_name



def test_public_api_guides_have_function_by_function_examples():
    root = Path(__file__).resolve().parents[1]
    docs = {
        "markdown": (root / "docs" / "user_guide.md").read_text(encoding="utf-8"),
        "latex": (root / "docs" / "user_guide.tex").read_text(encoding="utf-8"),
        "sphinx": (root / "docs" / "sphinx" / "source" / "user_guide.rst").read_text(encoding="utf-8"),
    }
    required_snippets = [
        "xa.open_database(",
        "xa.set_data_path(",
        "xa.get_data_path(",
        "xa.find_atdb_file(",
        "xa.resolve_atdb_path(",
        "xa.get_levels(",
        "xa.get_lines(",
        "xa.get_wavelengths(",
        "xa.get_energies(",
        "xa.match_line(",
        "xa.match_lines(",
        "xa.get_collisions(",
        "xa.get_photoionization(",
        "xa.get_recombination(",
        "xa.calc_emissivity(",
        "xa.LocalPlasmaState(",
        "xa.RadiationField.from_pairs(",
        "xa.EscapeContext(",
        "xa.context_from_values(",
        "xa.context_from_xstar_run(",
        "xa.calc_rate(",
        "isinstance(rate, xa.RateEvaluation)",
        "xa.calc_triplet(",
        "xa.solve_populations(",
        "xa.build_matrix(",
        "db.context.from_values(",
        "db.context.from_xstar_run(",
        "db.rates.type50(",
        "db.audit.type50_line_pumping(",
        "db.validate.compare_xstar_run(",
        "db.solve.ion(",
        "db.matrix.build_ion(",
    ]
    for name, text in docs.items():
        for snippet in required_snippets:
            assert snippet in text, f"{snippet} missing from {name} user guide"


def test_latex_examples_migration_table_uses_breakable_paths():
    root = Path(__file__).resolve().parents[1]
    tex = (root / "docs" / "user_guide.tex").read_text(encoding="utf-8")
    assert "\\path|51_run_helike_local_state_validation.py|" in tex
    assert "\\path|xstar_atomic.validate.summarize_local_state_comparison(...)|" in tex
    assert "\\begin{longtable}{p{0.34\\linewidth}p{0.58\\linewidth}}" in tex
