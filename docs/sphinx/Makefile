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

latexpdf:
	@$(SPHINXBUILD) -W --keep-going -M latexpdf "$(SOURCEDIR)" "$(BUILDDIR)"

linkcheck:
	@$(SPHINXBUILD) -W --keep-going -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

release: html linkcheck

clean:
	rm -rf "$(BUILDDIR)"
