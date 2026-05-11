"""Data-location and download helpers for XSTAR ``atdb.fits``.

The package does not bundle the large XSTAR atomic database.  These helpers
record a local data directory in the project-level ``datapath`` file and optionally
retrieve ``atdb.fits`` from the public HEASARC/LHEASOFT distribution.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional, Union

DEFAULT_ATDB_URL = (
    "https://heasarc.gsfc.nasa.gov/FTP/software/lheasoft/lheasoft6.36/"
    "heasoft-6.36/ftools/xstar/data/atdb.fits"
)
ATDB_FILENAME = "atdb.fits"
PACKAGE_DIR = Path(__file__).resolve().parent


def _project_root_from_source_tree() -> Optional[Path]:
    """Return the repository/source-tree root when running from ``src/``.

    In editable or ``PYTHONPATH=src`` development use, ``__file__`` is usually
    ``<repo>/src/xstar_atomic/data.py``.  Large downloaded data should not be
    written under ``src/`` because that directory is package source code.  In
    that case the preferred data directory is ``<repo>/data`` and the datapath
    file is ``<repo>/datapath`` (for example, in a project checkout named
    ``xstar_atomic``, this is ``xstar_atomic/datapath`` rather than
    ``xstar_atomic/src/xstar_atomic/datapath``).

    For installed wheels, where the package is not under a ``src`` directory,
    the fallback remains the package directory itself.
    """
    src_dir = PACKAGE_DIR.parent
    root = src_dir.parent
    if src_dir.name == "src" and (root / "pyproject.toml").exists():
        return root
    return None


PROJECT_ROOT = _project_root_from_source_tree()
DEFAULT_DATA_DIR = (PROJECT_ROOT / "data") if PROJECT_ROOT is not None else (PACKAGE_DIR / "data")
DATAPATH_FILE = (PROJECT_ROOT / "datapath") if PROJECT_ROOT is not None else (PACKAGE_DIR / "datapath")


def _format_bytes(n: Optional[int]) -> str:
    if n is None:
        return "unknown size"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{n} B"


def _remote_file_size(url: str) -> Optional[int]:
    """Return Content-Length for *url*, if available."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as response:
            size = response.headers.get("Content-Length")
            return int(size) if size else None
    except Exception:
        return None


def _normalize_data_dir(path: Union[str, Path]) -> Path:
    p = Path(path).expanduser()
    if p.name == ATDB_FILENAME:
        p = p.parent
    return p.resolve()


def set_data_path(path: Union[str, Path]) -> Path:
    """Record the local XSTAR atomic-data directory in the persistent datapath file.

    ``path`` may be either a directory containing ``atdb.fits`` or the full path
    to ``atdb.fits``.  The stored value is always the data directory.
    """
    data_dir = _normalize_data_dir(path)
    DATAPATH_FILE.write_text(str(data_dir) + "\n", encoding="utf-8")
    return data_dir


def get_data_path() -> Optional[Path]:
    """Return the configured data directory, or ``None`` if not configured."""
    if not DATAPATH_FILE.exists():
        return None
    text = DATAPATH_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _atdb_file_problem(path: Path) -> Optional[str]:
    """Return a short validation problem for an ``atdb.fits`` candidate.

    This lightweight check catches the common case where a relative path points
    to a zero-byte placeholder or interrupted download before ``astropy`` emits
    a lower-level FITS error.  It intentionally avoids opening the full 830 MB
    file.
    """
    try:
        if not path.exists():
            return "does not exist"
        if not path.is_file():
            return "is not a regular file"
        size = path.stat().st_size
        if size <= 0:
            return "is empty"
        if size < 2880:
            return f"is too small to be a FITS file ({size} bytes)"
        with path.open("rb") as handle:
            header = handle.read(80)
        if not header.startswith(b"SIMPLE"):
            return "does not start with a FITS SIMPLE header"
    except OSError as exc:
        return f"could not be read: {exc}"
    return None


def find_atdb_file(path: Optional[Union[str, Path]] = None, *, remember: bool = True) -> Optional[Path]:
    """Find ``atdb.fits`` from an explicit path, environment, datapath, or default.

    The environment variables ``XSTAR_ATDB_FITS`` and ``XSTAR_ATDB`` are honored
    as conveniences. ``XSTAR_ATDB`` is accepted because many benchmark scripts
    and user shell sessions naturally use that shorter name. If an explicit path
    or environment path is valid and ``remember`` is true,
    its parent directory is written to the persistent datapath file.  General
    command-line examples now call :func:`resolve_atdb_path` with the default
    ``remember_explicit=False`` so normal runs do not overwrite ``datapath``.
    """
    candidates: list[tuple[Path, bool]] = []
    if path is not None and str(path).strip():
        p = Path(path).expanduser()
        candidates.append((p / ATDB_FILENAME if p.is_dir() else p, remember))
    for env_name in ("XSTAR_ATDB_FITS", "XSTAR_ATDB"):
        env_path = os.environ.get(env_name)
        if env_path and env_path.strip():
            p = Path(env_path).expanduser()
            candidates.append((p / ATDB_FILENAME if p.is_dir() else p, remember))
    dp = get_data_path()
    if dp is not None:
        candidates.append((dp / ATDB_FILENAME, False))
    candidates.append((DEFAULT_DATA_DIR / ATDB_FILENAME, False))

    for candidate, should_remember in candidates:
        try:
            c = candidate.resolve()
        except Exception:
            c = candidate
        if c.exists() and c.is_file() and _atdb_file_problem(c) is None:
            if should_remember:
                set_data_path(c.parent)
            return c
    return None


def _prompt_yes_default(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in ("", "y", "yes")


def _download_progress_bar(done: int, total: Optional[int], *, width: int = 28) -> str:
    """Return a one-line ASCII progress indicator for ``atdb.fits`` downloads."""
    if total and total > 0:
        frac = min(1.0, max(0.0, done / total))
        pct = int(round(frac * 100.0))
        nfill = min(width, int(round(frac * width)))
        bar = "#" * nfill + "-" * (width - nfill)
        return (
            f"xstar data: downloading atdb.fits "
            f"[{bar}] {pct:3d}% ({_format_bytes(done)}/{_format_bytes(total)})"
        )
    # Unknown total size: keep a moving indicator with bytes downloaded.
    blocks = (done // (1024 * 1024)) % (width + 1)
    bar = "#" * int(blocks) + "-" * (width - int(blocks))
    return f"xstar data: downloading atdb.fits [{bar}] {_format_bytes(done)}"


def _copy_url_with_progress(url: str, destination: Path, expected_size: Optional[int] = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as response, tmp.open("wb") as out:
        total = expected_size
        if total is None:
            size_header = response.headers.get("Content-Length")
            total = int(size_header) if size_header else None
        done = 0
        last_render_len = 0
        # Print one horizontal progress bar and update it in place.
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            line = _download_progress_bar(done, total)
            padding = " " * max(0, last_render_len - len(line))
            print("\r" + line + padding, file=sys.stderr, end="", flush=True)
            last_render_len = len(line)
        # Ensure the final display reaches 100% when the server reports a total.
        if total:
            done_for_display = max(done, total) if done >= total else done
            line = _download_progress_bar(done_for_display, total)
        else:
            line = _download_progress_bar(done, total)
        padding = " " * max(0, last_render_len - len(line))
        print("\r" + line + padding, file=sys.stderr, flush=True)
    os.replace(tmp, destination)


def download_data(
    url: str = DEFAULT_ATDB_URL,
    destination: Optional[Union[str, Path]] = None,
    *,
    prompt: bool = True,
) -> Path:
    """Download or configure XSTAR ``atdb.fits`` and return its path.

    Parameters
    ----------
    url:
        Public URL to the XSTAR ``atdb.fits`` file.
    destination:
        Destination directory, or full destination filename.  The default is
        ``data`` at the source-tree root when running from ``PYTHONPATH=src``
        (for example ``/path/to/xstar_atomic/data``), or ``xstar_atomic/data``
        inside the installed package otherwise.
    prompt:
        If true, ask before downloading and allow the user to enter an existing
        local ``atdb.fits`` path instead.

    Notes
    -----
    Pressing Enter at the download prompt means yes.  Pressing Enter at the
    destination prompt uses the project-level ``data`` directory when running
    from a source tree, not ``src/xstar_atomic/data``.
    """
    size = _remote_file_size(url)
    print(f"XSTAR atdb.fits URL: {url}")
    print(f"Remote file size: {_format_bytes(size)}")

    if prompt:
        if not _prompt_yes_default("Download atdb.fits? [Y/n]: "):
            local = input("Enter full path to existing atdb.fits: ").strip()
            if not local:
                raise FileNotFoundError("No atdb.fits path provided")
            path = Path(local).expanduser().resolve()
            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"atdb.fits not found: {path}")
            set_data_path(path.parent)
            print(f"Saved data path: {path.parent}")
            return path
        default_dest = DEFAULT_DATA_DIR
        dest_text = input(f"Destination directory [{default_dest}]: ").strip()
        destination = dest_text or destination or default_dest
    else:
        destination = destination or DEFAULT_DATA_DIR

    dest = Path(destination).expanduser()
    if dest.name == ATDB_FILENAME:
        out_path = dest.resolve()
        data_dir = out_path.parent
    else:
        data_dir = dest.resolve()
        out_path = data_dir / ATDB_FILENAME

    print(f"Downloading to: {out_path}")
    _copy_url_with_progress(url, out_path, expected_size=size)
    set_data_path(data_dir)
    print(f"Saved data path: {data_dir}")
    return out_path


def resolve_atdb_path(
    path: Optional[Union[str, Path]] = None,
    *,
    prompt: bool = True,
    remember_explicit: bool = False,
) -> Path:
    """Resolve an ``atdb.fits`` path, prompting/download if needed.

    An explicitly supplied path has strict precedence over any configured
    environment or saved datapath.  If the explicit path is invalid, raise a
    clear error rather than silently falling back to ``XSTAR_ATDB_FITS``; this
    avoids surprising behavior in scripts and tests that intentionally pass a
    path argument.

    By default, ordinary explicit path use does **not** rewrite the persistent
    ``datapath`` file.  Use :func:`set_data_path`, ``python -m xstar_atomic.data
    --set-path ...``, or pass ``remember_explicit=True`` when the user is
    deliberately configuring the shared data location.  This keeps diagnostic
    examples from changing ``datapath`` simply because a command line included
    ``../xstar/data/atdb.fits``.
    """
    if path is not None and str(path).strip():
        p = Path(path).expanduser()
        candidate = p / ATDB_FILENAME if p.is_dir() else p
        try:
            candidate = candidate.resolve()
        except Exception:
            pass
        problem = _atdb_file_problem(candidate)
        if problem is None:
            if remember_explicit:
                set_data_path(candidate.parent)
            return candidate
        raise FileNotFoundError(
            f"atdb.fits not found or invalid: {candidate} ({problem}). "
            "Check the relative path, set XSTAR_ATDB_FITS or XSTAR_ATDB to the real 830 MB atdb.fits, "
            "or run: python -m xstar_atomic.data --set-path /path/to/atdb.fits"
        )

    found = find_atdb_file(None)
    if found is not None:
        return found
    if not prompt:
        raise FileNotFoundError(
            "No valid atdb.fits was found from XSTAR_ATDB_FITS, XSTAR_ATDB, datapath, or the default data directory. "
            "Configure it once with: python -m xstar_atomic.data --set-path /path/to/atdb.fits"
        )
    return download_data(prompt=prompt)


def main(argv: Optional[list[str]] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download or configure XSTAR atdb.fits for xstar-atomic")
    parser.add_argument("--url", default=DEFAULT_ATDB_URL, help="URL to atdb.fits")
    parser.add_argument("--destination", help="Destination directory or full atdb.fits filename")
    parser.add_argument("--set-path", help="Use an existing atdb.fits path and save its directory to datapath")
    parser.add_argument("--show", action="store_true", help="Show configured data path and resolved atdb.fits")
    parser.add_argument("--yes", action="store_true", help="Download without interactive prompts")
    args = parser.parse_args(argv)

    if args.set_path:
        path = Path(args.set_path).expanduser().resolve()
        problem = _atdb_file_problem(path)
        if problem is not None:
            raise FileNotFoundError(f"atdb.fits not found or invalid: {path} ({problem})")
        data_dir = set_data_path(path.parent)
        print(f"Saved data path: {data_dir}")
        print(path)
        return
    if args.show:
        data_dir = get_data_path()
        found = find_atdb_file(remember=False)
        print(f"datapath: {data_dir}")
        print(f"atdb.fits: {found}")
        return
    path = download_data(url=args.url, destination=args.destination, prompt=not args.yes)
    print(path)


if __name__ == "__main__":
    main()
