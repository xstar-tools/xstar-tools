SPHINXBUILD ?= sphinx-build
SOURCEDIR = ..
BUILDDIR = ../_build

.PHONY: help html latex latexpdf linkcheck release clean

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)"

html:
	@$(SPHINXBUILD) -W --keep-going -b html "$(SOURCEDIR)" "$(BUILDDIR)/html"

latex:
	@$(SPHINXBUILD) -W --keep-going -b latex "$(SOURCEDIR)" "$(BUILDDIR)/latex"
	@for image in backend_dispatch local_zone_solve controller_radial_flow publication_ownership; do \
		grep -q "$$image.eps" "$(BUILDDIR)/latex/xstar-tools.tex" || { \
			echo "ERROR: LaTeX output does not reference $$image.eps" >&2; exit 1; \
		}; \
	done

latexpdf:
	@$(SPHINXBUILD) -M latexpdf "$(SOURCEDIR)" "$(BUILDDIR)" -W --keep-going

linkcheck:
	@$(SPHINXBUILD) -W --keep-going -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

release: html linkcheck

clean:
	rm -rf "$(BUILDDIR)"
