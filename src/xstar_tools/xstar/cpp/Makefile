CXX ?= g++
PYTHON_CONFIG ?= python3-config
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra -Wpedantic
CPPFLAGS ?=
SO_LDFLAGS ?= -shared
OPACITY_STRICT_FP_FLAGS ?= -ffp-contract=off
THERMAL_STRICT_FP_FLAGS ?= -ffp-contract=off
ELEMENT_STRICT_FP_FLAGS ?= -ffp-contract=off

# v0.6.82.40.2.1 defaults to portable GCC -O3 for the ionization-regime work-equivalence audit.
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
V068240_PGO_MODE ?= $(V064897_PGO_MODE)
V068240_PROFILE_DIR ?= $(if $(filter-out $(CURDIR)/.v064897_pgo,$(V064897_PROFILE_DIR)),$(V064897_PROFILE_DIR),$(CURDIR)/.v068240_pgo)
V068240_NATIVE ?= $(V064897_NATIVE)
V068240_BUILD_PROFILE ?= portable-o3
V0682401_PRODUCTION_COMPILER ?= GCC

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
override CPPFLAGS += -DXSTAR_V068240_BUILD_PROFILE=\"$(V068240_BUILD_PROFILE)\"
ifneq ($(findstring -ffast-math,$(CXXFLAGS)),)
  $(error v0.6.82.40.1 rejects -ffast-math)
endif
ifneq ($(findstring -Ofast,$(CXXFLAGS)),)
  $(error v0.6.82.40.1 rejects -Ofast)
endif

COMMON_LIBS ?= -ldl -pthread
CFITSIO_CFLAGS ?= $(shell pkg-config --cflags cfitsio 2>/dev/null)
CFITSIO_LIBDIR ?= $(shell pkg-config --variable=libdir cfitsio 2>/dev/null)
CFITSIO_LIBS ?= $(shell pkg-config --libs cfitsio 2>/dev/null)
ifeq ($(strip $(CFITSIO_LIBS)),)
CFITSIO_LIBS := -lcfitsio
endif
CFITSIO_RPATH :=
ifneq ($(strip $(CFITSIO_LIBDIR)),)
CFITSIO_RPATH := -Wl,-rpath,$(CFITSIO_LIBDIR)
endif
override CPPFLAGS += $(CFITSIO_CFLAGS)
PYTHON_INCLUDES := $(shell $(PYTHON_CONFIG) --includes)
PYTHON_LIBS := $(shell $(PYTHON_CONFIG) --embed --ldflags)
PYTHON_LIBDIRS := $(patsubst -L%,%,$(filter -L%,$(PYTHON_LIBS)))
PYTHON_RPATHS := $(foreach d,$(PYTHON_LIBDIRS),-Wl,-rpath,$(d))
RPATH_ORIGIN := -Wl,-rpath,'$$ORIGIN'

# C++17 filesystem compatibility.  GCC 8 and some vendor toolchains require
# libstdc++fs, while current GNU libstdc++ accepts the extra compatibility
# library as well.  Use a deterministic default to avoid fragile parse-time
# $(shell ...) probes; callers using a non-GNU standard library may override
# this on the command line with FILESYSTEM_LIBS=.
FILESYSTEM_LINK_MODE ?= compatibility-default
FILESYSTEM_LIBS ?= -lstdc++fs

# Distribution version embedded in the Python-free xstar-cpp provenance sidecar.
# Keep the default local to this directory so `make all` is self-contained: no
# source/header/build input is read from a parent directory. Packaging may
# override PACKAGE_VERSION on the make command line.
PACKAGE_VERSION ?= 0.6.82.40.2.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.28.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.28
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.27.16.5
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.27.16.1
# Historical qualification compatibility marker: PACKAGE_VERSION ?= 0.6.82.27.16

SOLVER_TARGET := libxstar_solver.so
RATES_TARGET := libxstar_rates.so
MATRIX_TARGET := libxstar_matrix.so
EMISSIVITY_TARGET := libxstar_emissivity.so
OPACITY_TARGET := libxstar_opacity.so
THERMAL_TARGET := libxstar_thermal.so
LOCAL_ZONE_TARGET := libxstar_local_zone.so
FINAL_RECOMPUTE_TARGET := libxstar_final_recompute.so
PRODUCTION_ZONE_TARGET := libxstar_production_zone.so
XSPEC_TABLE_TARGET := libxstar_xspec_table.so
XSPEC_TABLE_EXECUTABLE := xstar-xspec-table
ENGINE_TARGET := libxstar_engine.so
API_TARGET := libxstar_api.so
CPP_BACKEND_TARGET := libxstar_backend_cpp.so
PYTHON_BACKEND_TARGET := libxstar_backend_python.so
EXECUTABLE_TARGET := xstar_cpp
PUBLIC_EXECUTABLE_TARGET := xstar-cpp
PUBLIC_EXECUTABLE_SOURCE := xstar_cpp_frontend.cpp
EXECUTABLE_OBJECTS := xstar_standalone.o xstar_science_fits.o xstar_run_state.o xstar_step_log.o xstar_atdb_runtime.o

PHYSICS_TARGETS := $(SOLVER_TARGET) $(RATES_TARGET) $(MATRIX_TARGET) \
	$(EMISSIVITY_TARGET) $(OPACITY_TARGET) $(THERMAL_TARGET) $(ENGINE_TARGET) $(LOCAL_ZONE_TARGET) $(FINAL_RECOMPUTE_TARGET) $(PRODUCTION_ZONE_TARGET) $(XSPEC_TABLE_TARGET)
STANDALONE_TARGETS := $(API_TARGET) $(CPP_BACKEND_TARGET) $(PYTHON_BACKEND_TARGET) $(EXECUTABLE_TARGET) $(PUBLIC_EXECUTABLE_TARGET) $(XSPEC_TABLE_EXECUTABLE)
TARGETS := $(PHYSICS_TARGETS) $(STANDALONE_TARGETS)

PUBLIC_HEADERS := xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_api.hpp xstar_element_engine.h xstar_spectral_engine.h xstar_thermal_engine.h xstar_local_zone_engine.h xstar_production_zone_bridge.h xstar_xspec_table.h
INTERNAL_HEADERS := xstar_standalone_internal.hpp xstar_local_zone_internal.hpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp source_real_energy_grid.hpp

.PHONY: all physics standalone test clean install print-config

all: $(TARGETS)
physics: $(PHYSICS_TARGETS)
standalone: $(STANDALONE_TARGETS)

$(SOLVER_TARGET): level_population.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ $<

$(RATES_TARGET): rate_kernels.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ $<

$(MATRIX_TARGET): matrix_kernels.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ $<

$(EMISSIVITY_TARGET): line_emissivity.cpp xstar_spectral_engine.h $(OPACITY_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ line_emissivity.cpp -L. -lxstar_opacity $(RPATH_ORIGIN)

$(OPACITY_TARGET): opacity_kernels.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(OPACITY_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ opacity_kernels.cpp

$(THERMAL_TARGET): thermal_kernels.cpp xstar_thermal_engine.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ thermal_kernels.cpp

$(ENGINE_TARGET): xstar_engine.cpp element_engine.cpp source_order_thermal_reducer.hpp canonical_thermal_term.hpp xstar_element_engine.h xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp $(SOLVER_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(ELEMENT_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ xstar_engine.cpp element_engine.cpp -L. -lxstar_solver $(RPATH_ORIGIN)

$(LOCAL_ZONE_TARGET): local_zone_engine.cpp xstar_local_zone_internal.hpp source_real_energy_grid.hpp source_order_thermal_reducer.hpp canonical_thermal_term.hpp xstar_local_zone_engine.h xstar_element_engine.h xstar_spectral_engine.h $(ENGINE_TARGET) $(EMISSIVITY_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ local_zone_engine.cpp -L. -lxstar_engine -lxstar_emissivity $(RPATH_ORIGIN)

$(FINAL_RECOMPUTE_TARGET): final_recompute_bridge.cpp xstar_final_recompute_bridge.h xstar_atdb_runtime.cpp xstar_atdb_runtime.hpp xstar_local_zone_engine.h $(LOCAL_ZONE_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ final_recompute_bridge.cpp xstar_atdb_runtime.cpp -L. -lxstar_local_zone $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PRODUCTION_ZONE_TARGET): xstar_standalone.cpp xstar_local_zone_internal.hpp xstar_production_zone_bridge.h xstar_science_fits.cpp xstar_run_state.cpp xstar_step_log.cpp xstar_atdb_runtime.cpp xstar_api.h xstar_local_zone_engine.h xstar_thermal_engine.h $(API_TARGET) $(LOCAL_ZONE_TARGET) $(EMISSIVITY_TARGET) $(THERMAL_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ xstar_standalone.cpp xstar_science_fits.cpp xstar_run_state.cpp xstar_step_log.cpp xstar_atdb_runtime.cpp -L. -lxstar_api -lxstar_local_zone -lxstar_emissivity -lxstar_thermal $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(XSPEC_TABLE_TARGET): xstar_xspec_table.cpp xstar_xspec_table.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ xstar_xspec_table.cpp $(CFITSIO_LIBS) $(CFITSIO_RPATH)

$(XSPEC_TABLE_EXECUTABLE): xstar_xspec_table_cli.cpp xstar_xspec_table_writer.cpp xstar_xspec_table_internal.hpp xstar_xspec_table.cpp xstar_xspec_table.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ xstar_xspec_table_cli.cpp xstar_xspec_table_writer.cpp xstar_xspec_table.cpp $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(FILESYSTEM_LIBS)

$(API_TARGET): xstar_api.cpp compiled_case.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -DXSTAR_API_BUILD $(SO_LDFLAGS) \
		-o $@ xstar_api.cpp compiled_case.cpp $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(CPP_BACKEND_TARGET): xstar_backend_cpp.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp $(PHYSICS_TARGETS) $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) \
		-o $@ xstar_backend_cpp.cpp -L. -lxstar_api $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PYTHON_BACKEND_TARGET): xstar_backend_python.cpp xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_standalone_internal.hpp $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(PYTHON_INCLUDES) $(SO_LDFLAGS) \
		-o $@ xstar_backend_python.cpp -L. -lxstar_api $(PYTHON_LIBS) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(PYTHON_RPATHS) $(RPATH_ORIGIN)

xstar_standalone.o: xstar_standalone.cpp xstar_local_zone_internal.hpp source_real_energy_grid.hpp xstar_science_fits.hpp xstar_run_state.hpp xstar_step_log.hpp xstar_atdb_runtime.hpp xstar_api.h xstar_api.hpp xstar_python_bridge.h xstar_local_zone_engine.h xstar_thermal_engine.h xstar_spectral_engine.h
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_science_fits.o: xstar_science_fits.cpp xstar_science_fits.hpp xstar_run_state.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_run_state.o: xstar_run_state.cpp xstar_run_state.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_step_log.o: xstar_step_log.cpp xstar_step_log.hpp xstar_run_state.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

xstar_atdb_runtime.o: xstar_atdb_runtime.cpp xstar_atdb_runtime.hpp xstar_local_zone_engine.h xstar_run_state.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -c -o $@ $<

$(EXECUTABLE_TARGET): $(EXECUTABLE_OBJECTS) $(API_TARGET) $(LOCAL_ZONE_TARGET) $(EMISSIVITY_TARGET) $(THERMAL_TARGET) $(CPP_BACKEND_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ $(EXECUTABLE_OBJECTS) \
		-L. -lxstar_api -lxstar_local_zone -lxstar_emissivity -lxstar_thermal $(CFITSIO_LIBS) $(CFITSIO_RPATH) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PUBLIC_EXECUTABLE_TARGET): $(EXECUTABLE_TARGET) $(API_TARGET) $(PRODUCTION_ZONE_TARGET) $(PUBLIC_EXECUTABLE_SOURCE)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -DXSTAR_TOOLS_PACKAGE_VERSION=\"$(PACKAGE_VERSION)\" -o $@ $(PUBLIC_EXECUTABLE_SOURCE) \
		-L. -lxstar_api -lxstar_production_zone $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

print-config:
	@echo CXX=$(CXX)
	@echo PYTHON_CONFIG=$(PYTHON_CONFIG)
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
	@echo V068240_BUILD_PROFILE=$(V068240_BUILD_PROFILE)
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
	./$(EXECUTABLE_TARGET) fixed-state-self-test --case-dir ../../../../tests/fixtures/historical/v06485_active_family_phase2_fixture
	./$(EXECUTABLE_TARGET) fixed-state-batch-self-test --case-dir ../../../../tests/fixtures/historical/v06485_active_family_phase2_fixture --batch 4
	rm -rf .v06485_native_output
	./$(EXECUTABLE_TARGET) run-fixed-state --case-dir ../../../../tests/fixtures/historical/v06485_active_family_phase2_fixture --output-dir .v06485_native_output
	test -s .v06485_native_output/xout_step.log
	test -s .v06485_native_output/xout_native_state.fits
	test -s .v06485_native_output/visited_records.csv
	rm -rf .v06485_native_output
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) self-test --backend python --plugin-dir . --python-path ../../.. --batch 4
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) python-bridge-test --plugin-dir . --python-path ../../..

install: all
	@echo "v0.6.48.7.4 keeps headers, C++ sources, shared libraries, executable, and Makefile in:"
	@pwd

clean:
	rm -f $(TARGETS) *.o
