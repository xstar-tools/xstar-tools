SPHINXBUILD ?= sphinx-build
PYTHON ?= python
SOURCEDIR = ..
BUILDDIR = ../_build
LATEXDOC = xstar-tools

.PHONY: help html latex latexpdf linkcheck release clean

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)"

html:
	@$(SPHINXBUILD) -W --keep-going -b html "$(SOURCEDIR)" "$(BUILDDIR)/html"

latex:
	@$(SPHINXBUILD) -W --keep-going -b latex "$(SOURCEDIR)" "$(BUILDDIR)/latex"
	@$(PYTHON) "$(SOURCEDIR)/_ext/normalize_latex_eps_references.py" "$(BUILDDIR)/latex/$(LATEXDOC).tex"

latexpdf: latex
	cd "$(BUILDDIR)/latex" && \
	latex -interaction=nonstopmode -halt-on-error $(LATEXDOC).tex && \
	latex -interaction=nonstopmode -halt-on-error $(LATEXDOC).tex && \
	dvips -o $(LATEXDOC).ps $(LATEXDOC).dvi && \
	ps2pdf $(LATEXDOC).ps $(LATEXDOC).pdf

linkcheck:
	@$(SPHINXBUILD) -W --keep-going -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck"

release: html linkcheck

clean:
	rm -rf "$(BUILDDIR)"
