from pathlib import Path


def test_user_guides_and_sphinx_scaffold_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "user_guide.md").is_file()
    assert (root / "docs" / "user_guide.tex").is_file()
    assert (root / "docs" / "sphinx" / "source" / "conf.py").is_file()
    assert (root / "docs" / "sphinx" / "source" / "api.rst").is_file()
    assert (root / "examples" / "06_high_level_api_quickstart.py").is_file()
