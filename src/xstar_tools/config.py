"""Stable public run configuration for :mod:`xstar_tools`.

This module is a productization layer.  It normalizes user-facing input sources
without implementing XSTAR science; execution remains delegated to the frozen
qualified paths in :mod:`xstar_tools.execution`.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
import re
import shlex
from typing import Any, Mapping

from .execution import BackendMode, normalize_mode, resolve_mode


_ADVANCED_BACKEND_KEYS = {
    "backend", "solver_backend", "rates_backend", "matrix_backend",
    "emissivity_backend", "opacity_backend", "thermal_backend", "engine_backend",
}
_BACKEND_VALUES = {"python", "cpp"}


def _literal_kind(value: Any) -> str:
    """Infer a HEASoft/IRAF parameter scalar type without changing its value."""
    if isinstance(value, bool):
        return "b"
    if isinstance(value, int) and not isinstance(value, bool):
        return "i"
    if isinstance(value, float):
        return "r"
    text = str(value).strip()
    if text.lower() in {"yes", "no", "true", "false", "t", "f"}:
        return "b"
    if re.fullmatch(r"[+-]?\d+", text):
        return "i"
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?", text):
        return "r"
    return "s"


def _format_parameter_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _parse_command_text(text: str) -> dict[str, Any]:
    """Parse ``xstar key=value`` text while preserving value literals."""
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    result: dict[str, Any] = {}
    for token in lexer:
        if token == "\\" or token.lower() == "xstar" or "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip().lower()
        if key:
            result[key] = value
    return result


def read_xstar_parameter_file(path: str | Path) -> dict[str, Any]:
    """Read an XSTAR parameter source into a canonical mapping.

    Supported inputs are HEASoft/IRAF-style ``.par`` rows
    (``name,type,mode,value,min,max,prompt``) and command-style files containing
    ``xstar key=value ...``.  Textual numeric literals are preserved rather than
    round-tripped through binary floating point.
    """
    p = Path(path).expanduser().resolve()
    text = p.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if p.suffix.lower() in {".sh", ".cmd"} or stripped.startswith("xstar ") or " xstar " in stripped[:200]:
        return _parse_command_text(text.replace("\\\n", " "))

    rows: dict[str, Any] = {}
    for raw in csv.reader(text.splitlines()):
        if not raw:
            continue
        first = raw[0].strip()
        if not first or first.startswith("#"):
            continue
        if len(raw) >= 4:
            rows[first.lower()] = raw[3].strip()
        elif len(raw) == 1 and "=" in raw[0]:
            key, value = raw[0].split("=", 1)
            rows[key.strip().lower()] = value.strip()
        else:
            raise ValueError(f"unsupported XSTAR parameter row in {p}: {raw!r}")
    if not rows:
        # A command split over unusual whitespace is still worth one final try.
        rows = _parse_command_text(text.replace("\\\n", " "))
    if not rows:
        raise ValueError(f"no XSTAR parameters found in {p}")
    return rows


def write_xstar_parameter_file(parameters: Mapping[str, Any], path: str | Path) -> Path:
    """Write a deterministic HEASoft/IRAF-style XSTAR ``.par`` file."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for name in sorted(str(k).strip().lower() for k in parameters):
            value = parameters[name]
            writer.writerow([name, _literal_kind(value), "h", _format_parameter_value(value), "", "", name])
    return target


def parameters_to_xstar_command(parameters: Mapping[str, Any]) -> str:
    """Return a deterministic shell-safe ``xstar key=value ...`` command."""
    tokens = ["xstar"]
    for name in sorted(str(k).strip().lower() for k in parameters):
        value = _format_parameter_value(parameters[name])
        tokens.append(f"{name}={shlex.quote(value)}")
    return " ".join(tokens)


@dataclass(frozen=True)
class XStarConfig:
    """Validated configuration for one stable public XSTAR run.

    Exactly one input source is required: ``input_file``, ``parameters`` or
    ``fortran_run_directory``.  Use the named constructors for the clearest API.

    ``overwrite=False`` gives the public API a deterministic output-directory
    policy: a non-empty existing directory is rejected before science executes.
    With ``overwrite=True`` the directory is replaced before the run.
    """

    input_file: Path | str | None = None
    data_dir: Path | str | Any | None = None
    output_dir: Path | str = "run1"
    mode: BackendMode | str = BackendMode.PURE_PYTHON
    threads: int = 1
    progress: bool = True
    log_level: str = "INFO"
    reproducible: bool = True
    overwrite: bool = False
    cache_dir: Path | str | None = None
    use_cache: bool = True
    rebuild_cache: bool = False
    advanced_backend_overrides: Mapping[str, str] = field(default_factory=dict)
    parameters: Mapping[str, Any] | None = field(default=None, repr=False)
    fortran_run_directory: Path | str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        sources = [self.input_file is not None, self.parameters is not None, self.fortran_run_directory is not None]
        if sum(bool(x) for x in sources) != 1:
            raise ValueError("exactly one input source is required: input_file, parameters, or fortran_run_directory")
        if int(self.threads) < 1:
            raise ValueError("threads must be >= 1")
        mode_name = normalize_mode(self.mode)
        object.__setattr__(self, "mode", BackendMode(mode_name))
        object.__setattr__(self, "output_dir", Path(self.output_dir).expanduser().resolve())
        if self.input_file is not None:
            object.__setattr__(self, "input_file", Path(self.input_file).expanduser().resolve())
        if self.cache_dir is not None:
            object.__setattr__(self, "cache_dir", Path(self.cache_dir).expanduser().resolve())
        if self.fortran_run_directory is not None:
            object.__setattr__(self, "fortran_run_directory", Path(self.fortran_run_directory).expanduser().resolve())
        if self.parameters is not None:
            object.__setattr__(self, "parameters", {str(k).strip().lower(): v for k, v in self.parameters.items()})

        overrides = {str(k).strip(): str(v).strip().lower() for k, v in dict(self.advanced_backend_overrides).items()}
        unknown = sorted(set(overrides) - _ADVANCED_BACKEND_KEYS)
        if unknown:
            raise ValueError("unknown advanced backend override(s): " + ", ".join(unknown))
        bad_values = sorted(k for k, v in overrides.items() if v not in _BACKEND_VALUES)
        if bad_values:
            raise ValueError("advanced backend overrides must be 'python' or 'cpp': " + ", ".join(bad_values))
        if overrides and mode_name in {"zone-cpp", "zone-all", "xstar-cpp"}:
            raise ValueError(f"advanced backend overrides are not compatible with monolithic mode {mode_name}")
        object.__setattr__(self, "advanced_backend_overrides", overrides)

        level = str(self.log_level).strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        object.__setattr__(self, "log_level", level)

    @classmethod
    def from_par_file(cls, path: str | Path, **kwargs: Any) -> "XStarConfig":
        return cls(input_file=path, **kwargs)

    @classmethod
    def from_mapping(cls, parameters: Mapping[str, Any], **kwargs: Any) -> "XStarConfig":
        return cls(parameters=dict(parameters), **kwargs)

    @classmethod
    def from_fortran_run_directory(cls, directory: str | Path, **kwargs: Any) -> "XStarConfig":
        return cls(fortran_run_directory=directory, **kwargs)

    @property
    def mode_name(self) -> str:
        return str(self.mode.value)

    @property
    def source_kind(self) -> str:
        if self.fortran_run_directory is not None:
            return "fortran-run-directory"
        if self.parameters is not None:
            return "mapping"
        return "par-file" if Path(self.input_file).suffix.lower() == ".par" else "input-file"

    def parameter_mapping(self) -> dict[str, Any]:
        if self.parameters is not None:
            return dict(self.parameters)
        if self.fortran_run_directory is not None:
            run_script = Path(self.fortran_run_directory) / "run_xstar.sh"
            if not run_script.is_file():
                raise FileNotFoundError(f"Fortran run directory has no run_xstar.sh: {run_script}")
            return read_xstar_parameter_file(run_script)
        if self.input_file is None or not Path(self.input_file).is_file():
            raise FileNotFoundError(f"XSTAR input file not found: {self.input_file}")
        return read_xstar_parameter_file(self.input_file)

    def source_run_script(self) -> Path | None:
        """Return an existing source-faithful run script when one is available."""
        if self.fortran_run_directory is not None:
            p = Path(self.fortran_run_directory) / "run_xstar.sh"
            if not p.is_file():
                raise FileNotFoundError(f"Fortran run directory has no run_xstar.sh: {p}")
            return p.resolve()
        if self.input_file is not None and Path(self.input_file).suffix.lower() in {".sh", ".cmd"}:
            if not Path(self.input_file).is_file():
                raise FileNotFoundError(f"XSTAR input file not found: {self.input_file}")
            return Path(self.input_file).resolve()
        return None

    def to_xstar_command(self) -> str:
        return parameters_to_xstar_command(self.parameter_mapping())

    def to_par_file(self, path: str | Path) -> Path:
        return write_xstar_parameter_file(self.parameter_mapping(), path)

    def validate(self) -> "XStarConfig":
        """Validate input/data/backend combinations without executing science."""
        self.parameter_mapping()  # validates the source and produces at least one parameter
        resolve_mode(self.mode_name)
        if self.data_dir is None:
            raise ValueError("data_dir is required for stable public XSTAR runs")
        from .data import XStarData
        data = self.data_dir if isinstance(self.data_dir, XStarData) else XStarData.from_directory(self.data_dir)
        data.validate()
        return self


__all__ = [
    "XStarConfig", "read_xstar_parameter_file", "write_xstar_parameter_file", "parameters_to_xstar_command",
]
