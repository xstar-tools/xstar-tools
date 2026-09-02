CXX ?= g++
MPICXX ?= mpic++
MPI_CXXFLAGS ?=
MPI_LDFLAGS ?=
PYTHON_CONFIG ?= python3-config
PKG_CONFIG ?= pkg-config
BREW ?= brew

# v0.6.88.3.2 macOS native-build link closure. The 0.6.88.3.1 Apple-only
# Type-77 exact-value compile closure is carried forward unchanged. Darwin
# additionally links libxstar_local_zone directly to libxstar_opacity because
# local_zone_engine.cpp calls its public ABI. Linux keeps its accepted link
# command unchanged.
HOST_UNAME_S := $(shell uname -s 2>/dev/null || echo Unknown)
ifeq ($(origin PLATFORM),command line)
  XSTAR_DETECTED_PLATFORM := $(PLATFORM)
else ifeq ($(OS),Windows_NT)
  XSTAR_DETECTED_PLATFORM := windows
else ifeq ($(HOST_UNAME_S),Darwin)
  XSTAR_DETECTED_PLATFORM := macos
else
  XSTAR_DETECTED_PLATFORM := linux
endif
# Deliberately override an unrelated environment variable named PLATFORM;
# callers select a platform explicitly with make PLATFORM=linux|macos|windows.
PLATFORM := $(XSTAR_DETECTED_PLATFORM)

# GNU make has a built-in CXX=g++ default. On macOS prefer the native Apple
# Clang driver unless the caller explicitly configured CXX via environment,
# makefile include, or command line. /usr/bin/g++ is normally an Apple-Clang
# alias, but spelling clang++ makes the supported compiler contract explicit.
ifeq ($(PLATFORM),macos)
  ifeq ($(origin CXX),default)
    CXX := clang++
  endif
endif

ifeq ($(PLATFORM),linux)
  SHLIB_EXT ?= .so
  EXEEXT ?=
  SHLIB_LDFLAGS ?= -shared
  PIC_FLAGS ?= -fPIC
  DL_LIBS ?= -ldl
  THREAD_LIBS ?= -pthread
  RPATH_ORIGIN ?= -Wl,-rpath,'$$ORIGIN'
  FILESYSTEM_LIBS ?= -lstdc++fs
else ifeq ($(PLATFORM),macos)
  SHLIB_EXT ?= .dylib
  EXEEXT ?=
  SHLIB_LDFLAGS ?= -dynamiclib
  PIC_FLAGS ?= -fPIC
  DL_LIBS ?=
  THREAD_LIBS ?= -pthread
  RPATH_ORIGIN ?= -Wl,-rpath,@loader_path
  FILESYSTEM_LIBS ?=
else ifeq ($(PLATFORM),windows)
  SHLIB_EXT ?= .dll
  EXEEXT ?= .exe
  SHLIB_LDFLAGS ?= -shared
  PIC_FLAGS ?=
  DL_LIBS ?=
  THREAD_LIBS ?= -pthread
  RPATH_ORIGIN ?=
  FILESYSTEM_LIBS ?=
else
  $(error unsupported PLATFORM=$(PLATFORM); expected linux, macos, or windows)
endif

# Shared-library target flags. Mach-O dylibs need an @rpath install name so
# the accepted @loader_path runtime rpath resolves sibling XSTAR libraries.
# Linux and Windows expand this to the historical SHLIB_LDFLAGS byte-for-byte.
ifeq ($(PLATFORM),macos)
  SHLIB_TARGET_LDFLAGS = $(SHLIB_LDFLAGS) -Wl,-install_name,@rpath/$@
  SHLIB_INSTALL_NAME_MODE ?= @rpath
else ifeq ($(PLATFORM),windows)
  SHLIB_TARGET_LDFLAGS = $(SHLIB_LDFLAGS) -Wl,--export-all-symbols -Wl,--enable-auto-import -Wl,--out-implib,$@.a
  SHLIB_INSTALL_NAME_MODE ?= pe-import-library
else
  SHLIB_TARGET_LDFLAGS = $(SHLIB_LDFLAGS)
  SHLIB_INSTALL_NAME_MODE ?= none
endif

# Darwin's linker requires libxstar_local_zone to name the dylib that directly
# defines xstar_opacity_apply_line_profile_v1. Linux preserves its accepted
# historical command stream; Windows linkage remains a later portability gate.
ifneq ($(filter $(PLATFORM),macos windows),)
  LOCAL_ZONE_LINK_LIBS ?= -lxstar_engine -lxstar_emissivity -lxstar_opacity
else
  LOCAL_ZONE_LINK_LIBS ?= -lxstar_engine -lxstar_emissivity
endif

# Historical caller compatibility: an explicitly supplied SO_LDFLAGS still
# overrides the new canonical SHLIB_LDFLAGS spelling.
ifneq ($(origin SO_LDFLAGS),undefined)
  SHLIB_LDFLAGS := $(SO_LDFLAGS)
endif

CXXFLAGS ?= -O3 -std=c++17 $(PIC_FLAGS) -Wall -Wextra -Wpedantic
CPPFLAGS ?=
OPACITY_STRICT_FP_FLAGS ?= -ffp-contract=off
THERMAL_STRICT_FP_FLAGS ?= -ffp-contract=off
ELEMENT_STRICT_FP_FLAGS ?= -ffp-contract=off

# v0.6.82.40.2.6 defaults to portable GCC -O3 for the ionization-regime work-equivalence audit.
# The .40.1 compiler experiment controls remain available but are not the audit variable.
# v0.6.82.40.1 GCC-only compiler/CPU experiment controls.  The default profile is
# deliberately equivalent to the accepted 0.6.82.39.2 portable -O3 build.
# Every non-default control is opt-in and must pass exact science/work/RSS
# qualification before it can be promoted.  These controls never enable
# -ffast-math, and the source-critical translation units retain the explicit
# -ffp-contract=off flags below.
#
# The historical v0.6.48.9.7 variables remain accepted as compatibility aliases
# so older host scripts do not silently change behavior.
V064897_PGO_MODE ?= off
V064897_PROFILE_DIR ?= $(CURDIR)/.v064897_pgo
V064897_NATIVE ?= 0

V068240_OPT_LEVEL ?= 3
V068240_LTO ?= 0
V068240_PGO_MODE ?= off
V068240_PROFILE_DIR ?= $(if $(filter-out $(CURDIR)/.v064897_pgo,$(V064897_PROFILE_DIR)),$(V064897_PROFILE_DIR),$(CURDIR)/.v068240_pgo)
V068240_NATIVE ?= 0
ifeq ($(PLATFORM),macos)
  V0682401_PRODUCTION_COMPILER ?= APPLECLANG
else ifeq ($(PLATFORM),windows)
  V0682401_PRODUCTION_COMPILER ?= MINGW64
else
  V0682401_PRODUCTION_COMPILER ?= GCC
endif

ifeq ($(filter $(V068240_OPT_LEVEL),2 3),)
  $(error v0.6.82.40.1 supports V068240_OPT_LEVEL=2 or 3)
endif
ifeq ($(filter $(V068240_PGO_MODE),off generate use),)
  $(error v0.6.82.40.1 supports V068240_PGO_MODE=off, generate, or use)
endif
ifeq ($(filter $(V068240_LTO),0 1),)
  $(error v0.6.82.40.1 supports V068240_LTO=0 or 1)
endif
ifeq ($(filter $(V068240_NATIVE),0 1),)
  $(error v0.6.82.40.1 supports V068240_NATIVE=0 or 1)
endif

# Last optimization flag wins, so this safely overrides the historical -O3 in
# the default CXXFLAGS while preserving callers that add unrelated flags.
override CXXFLAGS += -O$(V068240_OPT_LEVEL)
ifeq ($(V068240_LTO),1)
  override CXXFLAGS += -flto
endif
ifeq ($(V068240_PGO_MODE),generate)
  override CXXFLAGS += -fprofile-generate=$(V068240_PROFILE_DIR)
endif
ifeq ($(V068240_PGO_MODE),use)
  override CXXFLAGS += -fprofile-use=$(V068240_PROFILE_DIR) -fprofile-correction
endif
ifeq ($(V068240_NATIVE),1)
  override CXXFLAGS += -march=native
endif
ifneq ($(findstring -ffast-math,$(CXXFLAGS)),)
  $(error v0.6.82.40.1 rejects -ffast-math)
endif
ifneq ($(findstring -Ofast,$(CXXFLAGS)),)
  $(error v0.6.82.40.1 rejects -Ofast)
endif

COMMON_LIBS ?= $(DL_LIBS) $(THREAD_LIBS)

WINDOWS_PRODUCTION_ZONE_DEFINE :=
WINDOWS_BACKEND_DEFINE :=
WINDOWS_PYTHON_BACKEND_DEFINE :=
ifeq ($(PLATFORM),windows)
  WINDOWS_PRODUCTION_ZONE_DEFINE := -DXSTAR_PRODUCTION_ZONE_BUILD
  WINDOWS_BACKEND_DEFINE := -DXSTAR_BACKEND_BUILD
  WINDOWS_PYTHON_BACKEND_DEFINE := -DXSTAR_PYTHON_BACKEND_BUILD
endif

# CFITSIO discovery order:
#   1. caller-provided CFITSIO_* values;
#   2. pkg-config (all platforms);
#   3. `brew --prefix cfitsio` on macOS;
#   4. the historical linker-default -lcfitsio fallback.
CFITSIO_CFLAGS ?= $(shell $(PKG_CONFIG) --cflags cfitsio 2>/dev/null)
CFITSIO_LIBDIR ?= $(shell $(PKG_CONFIG) --variable=libdir cfitsio 2>/dev/null)
CFITSIO_LIBS ?= $(shell $(PKG_CONFIG) --libs cfitsio 2>/dev/null)
CFITSIO_DISCOVERY := pkg-config
CFITSIO_BREW_PREFIX :=
ifeq ($(strip $(CFITSIO_LIBS)),)
  ifeq ($(PLATFORM),macos)
    CFITSIO_BREW_PREFIX := $(shell $(BREW) --prefix cfitsio 2>/dev/null)
  endif
  ifneq ($(strip $(CFITSIO_BREW_PREFIX)),)
    CFITSIO_CFLAGS := -I$(CFITSIO_BREW_PREFIX)/include
    CFITSIO_LIBDIR := $(CFITSIO_BREW_PREFIX)/lib
    CFITSIO_LIBS := -L$(CFITSIO_LIBDIR) -lcfitsio
    CFITSIO_DISCOVERY := homebrew
  else
    CFITSIO_LIBS := -lcfitsio
    CFITSIO_DISCOVERY := linker-default
  endif
endif
CFITSIO_RPATH :=
ifneq ($(PLATFORM),windows)
ifneq ($(strip $(CFITSIO_LIBDIR)),)
CFITSIO_RPATH := -Wl,-rpath,$(CFITSIO_LIBDIR)
endif
endif
override CPPFLAGS += $(CFITSIO_CFLAGS)
PYTHON_INCLUDES := $(shell $(PYTHON_CONFIG) --includes)
PYTHON_LIBS := $(shell $(PYTHON_CONFIG) --embed --ldflags)
PYTHON_LIBDIRS := $(patsubst -L%,%,$(filter -L%,$(PYTHON_LIBS)))
PYTHON_RPATHS := $(foreach d,$(PYTHON_LIBDIRS),-Wl,-rpath,$(d))
ifeq ($(PLATFORM),windows)
  PYTHON_RPATHS :=
endif
# C++17 filesystem compatibility.  Linux preserves the accepted GCC 8
# compatibility link to libstdc++fs.  The platform block above leaves this
# empty for libc++/macOS and MinGW/Windows.  Callers may still override it.
FILESYSTEM_LINK_MODE ?= compatibility-default

# Distribution version embedded in the Python-free xstar-cpp provenance sidecar.
# Keep the default local to this directory so `make all` is self-contained: no
# source/header/build input is read from a parent directory. Packaging may
# override PACKAGE_VERSION on the make command line.
PACKAGE_VERSION ?= 0.6.88.5.6
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.3.2
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.3.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.3
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.2.2
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.2.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.2
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.88.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.84
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.28.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.28
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.27.16.5
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.27.16.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.27.16

SOLVER_TARGET := libxstar_solver$(SHLIB_EXT)
RATES_TARGET := libxstar_rates$(SHLIB_EXT)
MATRIX_TARGET := libxstar_matrix$(SHLIB_EXT)
EMISSIVITY_TARGET := libxstar_emissivity$(SHLIB_EXT)
OPACITY_TARGET := libxstar_opacity$(SHLIB_EXT)
THERMAL_TARGET := libxstar_thermal$(SHLIB_EXT)
LOCAL_ZONE_TARGET := libxstar_local_zone$(SHLIB_EXT)
FINAL_RECOMPUTE_TARGET := libxstar_final_recompute$(SHLIB_EXT)
PRODUCTION_ZONE_TARGET := libxstar_production_zone$(SHLIB_EXT)
XSPEC_TABLE_TARGET := libxstar_xspec_table$(SHLIB_EXT)
XSPEC_TABLE_EXECUTABLE := xstar-xspec-table$(EXEEXT)
XSPEC_INITABLE_EXECUTABLE := xstar-xspec-initable$(EXEEXT)
XSPEC_SERIAL_EXECUTABLE := xstar-xspec$(EXEEXT)
XSPEC_GRID_EXECUTABLE := $(XSPEC_SERIAL_EXECUTABLE)
XSPEC_MPI_EXECUTABLE := xstar-xspec-mpi$(EXEEXT)
ENGINE_TARGET := libxstar_engine$(SHLIB_EXT)
API_TARGET := libxstar_api$(SHLIB_EXT)
CPP_BACKEND_TARGET := libxstar_backend_cpp$(SHLIB_EXT)
PYTHON_BACKEND_TARGET := libxstar_backend_python$(SHLIB_EXT)
EXECUTABLE_TARGET := xstar_cpp$(EXEEXT)
PUBLIC_EXECUTABLE_TARGET := xstar-cpp$(EXEEXT)
PUBLIC_EXECUTABLE_SOURCE := xstar_cpp_frontend.cpp
EXECUTABLE_OBJECTS := xstar_standalone.o xstar_science_fits.o xstar_run_state.o xstar_step_log.o xstar_atdb_runtime.o xstar_dynamic_library.o

PHYSICS_TARGETS := $(SOLVER_TARGET) $(RATES_TARGET) $(MATRIX_TARGET) \
	$(EMISSIVITY_TARGET) $(OPACITY_TARGET) $(THERMAL_TARGET) $(ENGINE_TARGET) $(LOCAL_ZONE_TARGET) $(FINAL_RECOMPUTE_TARGET) $(PRODUCTION_ZONE_TARGET) $(XSPEC_TABLE_TARGET)
STANDALONE_TARGETS := $(API_TARGET) $(CPP_BACKEND_TARGET) $(PYTHON_BACKEND_TARGET) $(EXECUTABLE_TARGET) $(PUBLIC_EXECUTABLE_TARGET) $(XSPEC_TABLE_EXECUTABLE) $(XSPEC_INITABLE_EXECUTABLE) $(XSPEC_GRID_EXECUTABLE)
TARGETS := $(PHYSICS_TARGETS) $(STANDALONE_TARGETS)
MPI_TARGETS := $(XSPEC_MPI_EXECUTABLE)

PUBLIC_HEADERS := xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_api.hpp xstar_element_engine.h xstar_spectral_engine.h xstar_thermal_engine.h xstar_local_zone_engine.h xstar_production_zone_bridge.h xstar_xspec_table.h
INTERNAL_HEADERS := xstar_path_compat.hpp xstar_standalone_internal.hpp xstar_local_zone_internal.hpp xstar_element_engine_internal.hpp xstar_backend_common.hpp xstar_platform.hpp xstar_dynamic_library.hpp xstar_process.hpp compact_arrays.hpp error_codes.hpp source_real_energy_grid.hpp

.PHONY: all physics standalone mpi test clean install print-config

all: $(TARGETS)
physics: $(PHYSICS_TARGETS)
standalone: $(STANDALONE_TARGETS)

# MPI is deliberately opt-in.  Plain `make` / `make all` never requires an
# MPI compiler or runtime.  Windows MPI is intentionally out of scope; the
# accepted true-MPI path remains available on Linux/macOS when MPICXX exists.
ifeq ($(PLATFORM),windows)
mpi:
	@echo "xstar-xspec-mpi is not supported on PLATFORM=windows" >&2
	@exit 2
else
mpi: $(XSPEC_MPI_EXECUTABLE)
endif

$(SOLVER_TARGET): level_population.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ $<

$(RATES_TARGET): rate_kernels.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ $<

$(MATRIX_TARGET): matrix_kernels.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ $<

$(EMISSIVITY_TARGET): line_emissivity.cpp xstar_spectral_engine.h $(OPACITY_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ line_emissivity.cpp -L. -lxstar_opacity $(RPATH_ORIGIN)

$(OPACITY_TARGET): opacity_kernels.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(OPACITY_STRICT_FP_FLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ opacity_kernels.cpp

$(THERMAL_TARGET): thermal_kernels.cpp xstar_thermal_engine.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ thermal_kernels.cpp

$(ENGINE_TARGET): xstar_engine.cpp element_engine.cpp source_order_thermal_reducer.hpp canonical_thermal_term.hpp xstar_element_engine.h xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp $(SOLVER_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(ELEMENT_STRICT_FP_FLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ xstar_engine.cpp element_engine.cpp -L. -lxstar_solver $(RPATH_ORIGIN)

$(LOCAL_ZONE_TARGET): local_zone_engine.cpp xstar_process.hpp xstar_local_zone_internal.hpp source_real_energy_grid.hpp source_order_thermal_reducer.hpp canonical_thermal_term.hpp xstar_local_zone_engine.h xstar_element_engine.h xstar_spectral_engine.h $(ENGINE_TARGET) $(EMISSIVITY_TARGET) $(OPACITY_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ local_zone_engine.cpp -L. $(LOCAL_ZONE_LINK_LIBS) $(RPATH_ORIGIN)

$(FINAL_RECOMPUTE_TARGET): final_recompute_bridge.cpp xstar_process.hpp xstar_final_recompute_bridge.h xstar_atdb_runtime.cpp xstar_atdb_runtime.hpp xstar_local_zone_engine.h $(LOCAL_ZONE_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ final_recompute_bridge.cpp xstar_atdb_runtime.cpp -L. -lxstar_local_zone $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PRODUCTION_ZONE_TARGET): xstar_standalone.cpp xstar_process.hpp xstar_local_zone_internal.hpp xstar_production_zone_bridge.h xstar_science_fits.cpp xstar_run_state.cpp xstar_step_log.cpp xstar_atdb_runtime.cpp xstar_api.h xstar_local_zone_engine.h xstar_thermal_engine.h xstar_platform.hpp xstar_dynamic_library.hpp xstar_dynamic_library.o $(API_TARGET) $(LOCAL_ZONE_TARGET) $(EMISSIVITY_TARGET) $(THERMAL_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(WINDOWS_PRODUCTION_ZONE_DEFINE) $(THERMAL_STRICT_FP_FLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ xstar_standalone.cpp xstar_science_fits.cpp xstar_run_state.cpp xstar_step_log.cpp xstar_atdb_runtime.cpp xstar_dynamic_library.o -L. -lxstar_api -lxstar_local_zone -lxstar_emissivity -lxstar_thermal $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(XSPEC_TABLE_TARGET): xstar_xspec_table.cpp xstar_xspec_table.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SHLIB_TARGET_LDFLAGS) -o $@ xstar_xspec_table.cpp $(CFITSIO_LIBS) $(CFITSIO_RPATH)

$(XSPEC_TABLE_EXECUTABLE): xstar_xspec_table_cli.cpp xstar_xspec_table_writer.cpp xstar_xspec_table_internal.hpp xstar_xspec_table.cpp xstar_xspec_table.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ xstar_xspec_table_cli.cpp xstar_xspec_table_writer.cpp xstar_xspec_table.cpp $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(FILESYSTEM_LIBS)

$(XSPEC_INITABLE_EXECUTABLE): xstar_xspec_initable_cli.cpp xstar_xspec_initable.cpp xstar_xspec_initable_internal.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ xstar_xspec_initable_cli.cpp xstar_xspec_initable.cpp $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(FILESYSTEM_LIBS)

$(XSPEC_GRID_EXECUTABLE): xstar_xspec_parallel.cpp xstar_process.hpp xstar_platform.hpp $(XSPEC_INITABLE_EXECUTABLE) $(XSPEC_TABLE_EXECUTABLE) $(PUBLIC_EXECUTABLE_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ xstar_xspec_parallel.cpp $(FILESYSTEM_LIBS)

ifeq ($(PLATFORM),windows)
$(XSPEC_MPI_EXECUTABLE):
	@echo "xstar-xspec-mpi is not supported on PLATFORM=windows" >&2
	@exit 2
else
$(XSPEC_MPI_EXECUTABLE): xstar_xspec_mpi.cpp xstar_process.hpp $(XSPEC_INITABLE_EXECUTABLE) $(XSPEC_TABLE_EXECUTABLE) $(PUBLIC_EXECUTABLE_TARGET)
	$(MPICXX) $(CPPFLAGS) $(CXXFLAGS) $(MPI_CXXFLAGS) -o $@ xstar_xspec_mpi.cpp $(FILESYSTEM_LIBS) $(MPI_LDFLAGS)
endif

$(API_TARGET): xstar_api.cpp compiled_case.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp xstar_platform.hpp xstar_dynamic_library.hpp xstar_dynamic_library.o
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -DXSTAR_API_BUILD $(SHLIB_TARGET_LDFLAGS) \
		-o $@ xstar_api.cpp compiled_case.cpp xstar_dynamic_library.o $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(CPP_BACKEND_TARGET): xstar_backend_cpp.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp xstar_platform.hpp xstar_dynamic_library.hpp xstar_dynamic_library.o $(PHYSICS_TARGETS) $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(WINDOWS_BACKEND_DEFINE) $(SHLIB_TARGET_LDFLAGS) \
		-o $@ xstar_backend_cpp.cpp xstar_dynamic_library.o -L. -lxstar_api $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PYTHON_BACKEND_TARGET): xstar_backend_python.cpp xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_standalone_internal.hpp xstar_platform.hpp xstar_dynamic_library.hpp xstar_dynamic_library.o $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(PYTHON_INCLUDES) $(WINDOWS_PYTHON_BACKEND_DEFINE) $(SHLIB_TARGET_LDFLAGS) \
		-o $@ xstar_backend_python.cpp xstar_dynamic_library.o -L. -lxstar_api $(PYTHON_LIBS) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(PYTHON_RPATHS) $(RPATH_ORIGIN)

xstar_standalone.o: xstar_standalone.cpp xstar_process.hpp xstar_local_zone_internal.hpp source_real_energy_grid.hpp xstar_science_fits.hpp xstar_run_state.hpp xstar_step_log.hpp xstar_atdb_runtime.hpp xstar_api.h xstar_api.hpp xstar_python_bridge.h xstar_local_zone_engine.h xstar_thermal_engine.h xstar_spectral_engine.h xstar_platform.hpp xstar_dynamic_library.hpp xstar_path_compat.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<


xstar_dynamic_library.o: xstar_dynamic_library.cpp xstar_dynamic_library.hpp xstar_platform.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_science_fits.o: xstar_science_fits.cpp xstar_process.hpp xstar_science_fits.hpp xstar_run_state.hpp xstar_path_compat.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_run_state.o: xstar_run_state.cpp xstar_run_state.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_step_log.o: xstar_step_log.cpp xstar_step_log.hpp xstar_run_state.hpp xstar_path_compat.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_atdb_runtime.o: xstar_atdb_runtime.cpp xstar_atdb_runtime.hpp xstar_local_zone_engine.h xstar_run_state.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(EXECUTABLE_TARGET): $(EXECUTABLE_OBJECTS) $(API_TARGET) $(LOCAL_ZONE_TARGET) $(EMISSIVITY_TARGET) $(THERMAL_TARGET) $(CPP_BACKEND_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ $(EXECUTABLE_OBJECTS) \
		-L. -lxstar_api -lxstar_local_zone -lxstar_emissivity -lxstar_thermal $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PUBLIC_EXECUTABLE_TARGET): $(EXECUTABLE_TARGET) $(API_TARGET) $(PRODUCTION_ZONE_TARGET) $(PUBLIC_EXECUTABLE_SOURCE) xstar_process.hpp xstar_platform.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -DXSTAR_TOOLS_PACKAGE_VERSION=\"$(PACKAGE_VERSION)\" -o $@ $(PUBLIC_EXECUTABLE_SOURCE) \
		-L. -lxstar_api -lxstar_production_zone $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

print-config:
	@echo PLATFORM=$(PLATFORM)
	@echo SHLIB_EXT=$(SHLIB_EXT)
	@echo EXEEXT=$(EXEEXT)
	@echo SHLIB_LDFLAGS=$(SHLIB_LDFLAGS)
	@echo SHLIB_INSTALL_NAME_MODE=$(SHLIB_INSTALL_NAME_MODE)
	@echo PIC_FLAGS=$(PIC_FLAGS)
	@echo DL_LIBS=$(DL_LIBS)
	@echo THREAD_LIBS=$(THREAD_LIBS)
	@echo RPATH_ORIGIN=$(RPATH_ORIGIN)
	@echo CXX=$(CXX)
	@echo MPICXX=$(MPICXX)
	@echo MPI_CXXFLAGS=$(MPI_CXXFLAGS)
	@echo MPI_LDFLAGS=$(MPI_LDFLAGS)
	@echo PYTHON_CONFIG=$(PYTHON_CONFIG)
	@echo PKG_CONFIG=$(PKG_CONFIG)
	@echo BREW=$(BREW)
	@echo CFITSIO_DISCOVERY=$(CFITSIO_DISCOVERY)
	@echo CFITSIO_BREW_PREFIX=$(CFITSIO_BREW_PREFIX)
	@echo CFITSIO_CFLAGS=$(CFITSIO_CFLAGS)
	@echo CFITSIO_LIBDIR=$(CFITSIO_LIBDIR)
	@echo CFITSIO_LIBS=$(CFITSIO_LIBS)
	@echo CFITSIO_RPATH=$(CFITSIO_RPATH)
	@echo PYTHON_INCLUDES=$(PYTHON_INCLUDES)
	@echo PYTHON_LIBS=$(PYTHON_LIBS)
	@echo PYTHON_LIBDIRS=$(PYTHON_LIBDIRS)
	@echo PYTHON_RPATHS=$(PYTHON_RPATHS)
	@echo OPACITY_STRICT_FP_FLAGS=$(OPACITY_STRICT_FP_FLAGS)
	@echo THERMAL_STRICT_FP_FLAGS=$(THERMAL_STRICT_FP_FLAGS)
	@echo ELEMENT_STRICT_FP_FLAGS=$(ELEMENT_STRICT_FP_FLAGS)
	@echo V064897_PGO_MODE=$(V064897_PGO_MODE)
	@echo V064897_PROFILE_DIR=$(V064897_PROFILE_DIR)
	@echo V064897_NATIVE=$(V064897_NATIVE)
	@echo V068240_OPT_LEVEL=$(V068240_OPT_LEVEL)
	@echo V068240_LTO=$(V068240_LTO)
	@echo V068240_PGO_MODE=$(V068240_PGO_MODE)
	@echo V068240_PROFILE_DIR=$(V068240_PROFILE_DIR)
	@echo V068240_NATIVE=$(V068240_NATIVE)
	@echo V0682401_PRODUCTION_COMPILER=$(V0682401_PRODUCTION_COMPILER)
	@echo V068240_CXXFLAGS=$(CXXFLAGS)
	@echo FILESYSTEM_LINK_MODE=$(FILESYSTEM_LINK_MODE)
	@echo FILESYSTEM_LIBS=$(FILESYSTEM_LIBS)
	@echo PACKAGE_VERSION=$(PACKAGE_VERSION)

# These are ABI/scaffold tests only. They deliberately do not claim science parity.
test: all
	./$(EXECUTABLE_TARGET) list-backends
	./$(EXECUTABLE_TARGET) backend-info --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) self-test --backend cpp --plugin-dir . --batch 4
	./$(EXECUTABLE_TARGET) element-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) evaluation-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) construction-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) construction-evaluation-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) spectral-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) thermal-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) convergence-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) secant-ieee-self-test --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) fixed-state-self-test --case-dir ../../../../tests/fixtures/scaffold/v06486_fixed_state_regression_scaffold
	./$(EXECUTABLE_TARGET) fixed-state-batch-self-test --case-dir ../../../../tests/fixtures/scaffold/v06486_fixed_state_regression_scaffold --batch 4
	rm -rf .v06486_scaffold_output
	./$(EXECUTABLE_TARGET) run-fixed-state --case-dir ../../../../tests/fixtures/scaffold/v06486_fixed_state_regression_scaffold --output-dir .v06486_scaffold_output
	test -s .v06486_scaffold_output/xout_step.log
	test -s .v06486_scaffold_output/xout_native_state.fits
	test -s .v06486_scaffold_output/visited_records.csv
	rm -rf .v06486_scaffold_output
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) self-test --backend python --plugin-dir . --python-path ../../.. --batch 4
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) python-bridge-test --plugin-dir . --python-path ../../..

install: all
	@echo "v0.6.48.7.4 keeps headers, C++ sources, shared libraries, executable, and Makefile in:"
	@pwd

clean:
	rm -f $(TARGETS) $(MPI_TARGETS) *.o *.dll.a
