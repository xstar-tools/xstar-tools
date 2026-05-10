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
