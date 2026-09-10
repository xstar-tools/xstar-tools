"""Sphinx post-transform that converts SVG diagrams to EPS3 for LaTeX output.

HTML keeps using the original SVG assets.  The LaTeX builder is extended with
PostScript support and each SVG is converted with ImageMagick using the
``eps3:`` coder so the generated LaTeX path uses ``.eps`` files.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from docutils import nodes
from sphinx.transforms.post_transforms.images import ImageConverter
from sphinx.util import logging
from sphinx.util.osutil import ensuredir

logger = logging.getLogger(__name__)

EPS_MIMETYPE = "application/postscript"


def _imagemagick_command() -> list[str] | None:
    """Return an ImageMagick command prefix suitable for this host."""
    # Prefer the ImageMagick 7 launcher when available; ImageMagick 6
    # installations commonly expose only the historical ``convert`` binary.
    if shutil.which("magick"):
        return ["magick"]
    if os.name != "nt" and shutil.which("convert"):
        return ["convert"]
    return None


class SvgToEpsConverter(ImageConverter):
    """Convert SVG image nodes to EPS3 when the builder accepts PostScript."""

    conversion_rules = [("image/svg+xml", EPS_MIMETYPE)]

    def is_available(self) -> bool:
        return _imagemagick_command() is not None

    def handle(self, node: nodes.image) -> None:
        source_mimetype, target_mimetype = self.get_conversion_rule(node)
        if source_mimetype in node["candidates"]:
            srcpath = node["candidates"][source_mimetype]
        else:
            srcpath = node["candidates"]["*"]

        # Sphinx's built-in MIME-to-extension table does not include EPS, so
        # force the destination suffix here instead of get_filename_for().
        source_name = Path(self.env.images[srcpath][1])
        filename = source_name.with_suffix(".eps").name
        ensuredir(self.imagedir)
        destpath = self.imagedir / filename
        abs_srcpath = self.app.srcdir / srcpath

        if self.convert(abs_srcpath, destpath):
            if "*" in node["candidates"]:
                node["candidates"]["*"] = str(destpath)
            else:
                node["candidates"][target_mimetype] = str(destpath)
            node["uri"] = str(destpath)
            self.env.original_image_uri[destpath] = srcpath
            self.env.images.add_file(self.env.docname, destpath)

    def convert(self, _from: str | os.PathLike[str], _to: str | os.PathLike[str]) -> bool:
        command = _imagemagick_command()
        if command is None:
            logger.warning(
                "ImageMagick is required for LaTeX SVG-to-EPS conversion; "
                "install the 'convert' (POSIX) or 'magick' (Windows) command"
            )
            return False

        source = Path(_from)
        target = Path(_to)
        target.parent.mkdir(parents=True, exist_ok=True)
        argv = [*command, str(source), f"eps3:{target}"]
        logger.info("SVG->EPS3: %s", " ".join(argv))
        completed = subprocess.run(argv, text=True, capture_output=True)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown ImageMagick error"
            logger.warning("SVG-to-EPS conversion failed for %s: %s", source, detail)
            return False
        return True


def _enable_latex_eps(app) -> None:
    if app.builder.name != "latex":
        return
    supported = list(app.builder.supported_image_types)
    if EPS_MIMETYPE not in supported:
        supported.append(EPS_MIMETYPE)
        app.builder.supported_image_types = supported


def setup(app):
    app.connect("builder-inited", _enable_latex_eps)
    app.add_post_transform(SvgToEpsConverter)
    return {
        "version": "0.6.90.5.2",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
