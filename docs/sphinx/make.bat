@ECHO OFF
set SPHINXBUILD=sphinx-build
set SOURCEDIR=..
set BUILDDIR=..\_build
if "%1"=="" goto help
if "%1"=="html" %SPHINXBUILD% -W --keep-going -b html %SOURCEDIR% %BUILDDIR%\html
if "%1"=="latex" %SPHINXBUILD% -W --keep-going -b latex %SOURCEDIR% %BUILDDIR%\latex
if "%1"=="latexpdf" %SPHINXBUILD% -M latexpdf %SOURCEDIR% %BUILDDIR% -W --keep-going
if "%1"=="linkcheck" %SPHINXBUILD% -W --keep-going -b linkcheck %SOURCEDIR% %BUILDDIR%\linkcheck
if "%1"=="release" (
  %SPHINXBUILD% -W --keep-going -b html %SOURCEDIR% %BUILDDIR%\html && %SPHINXBUILD% -W --keep-going -b linkcheck %SOURCEDIR% %BUILDDIR%\linkcheck
)
if "%1"=="clean" rmdir /S /Q %BUILDDIR%
goto end
:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR%
:end
