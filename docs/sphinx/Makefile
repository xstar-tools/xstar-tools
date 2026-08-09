SPHINXBUILD ?= sphinx-build
SOURCEDIR = ..
BUILDDIR = ../_build

.PHONY: help html linkcheck release clean

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)"

html:
	@$(SPHINXBUILD) -W --keep-going -b html "$(SOURCEDIR)" "$(BUILDDIR)/html"

linkcheck:
	@$(SPHINXBUILD) -W --keep-going -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

release: html linkcheck

clean:
	rm -rf "$(BUILDDIR)"
