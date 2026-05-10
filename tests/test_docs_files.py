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
        "match_line",
        "get_collisions",
        "get_photoionization",
        "get_recombination",
        "calc_emissivity",
        "context_from_values",
        "context_from_xstar_run",
        "calc_rate",
        "calc_triplet",
        "solve_populations",
        "build_matrix",
        "db.rates.type50",
        "db.audit.type50_line_pumping",
        "db.validate.compare_xstar_run",
        "type50_bound_bound",
    ]
    for token in required_plain:
        assert token in md, token
        assert token in rst_user, token

    required_tex = [token.replace("_", "\\_") for token in required_plain]
    # Dotted object names in LaTeX are usually inside \\texttt{} but keep the
    # same escaped-underscore spelling.
    for token in required_tex:
        assert token in tex, token

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
