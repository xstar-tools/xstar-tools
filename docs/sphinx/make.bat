@ECHO OFF
set SPHINXBUILD=sphinx-build
set PYTHON=python
set SOURCEDIR=..
set BUILDDIR=..\_build
set LATEXDOC=xstar-tools
if "%1"=="" goto help
if "%1"=="html" %SPHINXBUILD% -W --keep-going -b html %SOURCEDIR% %BUILDDIR%\html
if "%1"=="latex" (
  %SPHINXBUILD% -W --keep-going -b latex %SOURCEDIR% %BUILDDIR%\latex || exit /b 1
  %PYTHON% %SOURCEDIR%\_ext\normalize_latex_eps_references.py %BUILDDIR%\latex\%LATEXDOC%.tex || exit /b 1
)
if "%1"=="latexpdf" (
  call "%~f0" latex || exit /b 1
  pushd %BUILDDIR%\latex || exit /b 1
  latex -interaction=nonstopmode -halt-on-error %LATEXDOC%.tex || (popd & exit /b 1)
  latex -interaction=nonstopmode -halt-on-error %LATEXDOC%.tex || (popd & exit /b 1)
  dvips -o %LATEXDOC%.ps %LATEXDOC%.dvi || (popd & exit /b 1)
  ps2pdf %LATEXDOC%.ps %LATEXDOC%.pdf || (popd & exit /b 1)
  popd
)
if "%1"=="linkcheck" %SPHINXBUILD% -W --keep-going -b linkcheck %SOURCEDIR% %BUILDDIR%\linkcheck
if "%1"=="release" (
  %SPHINXBUILD% -W --keep-going -b html %SOURCEDIR% %BUILDDIR%\html && %SPHINXBUILD% -W --keep-going -b linkcheck %SOURCEDIR% %BUILDDIR%\linkcheck
)
if "%1"=="clean" rmdir /S /Q %BUILDDIR%
goto end
:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR%
:end
