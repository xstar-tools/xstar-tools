CXX ?= g++
PYTHON_CONFIG ?= python3-config
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra -Wpedantic
CPPFLAGS ?=
SO_LDFLAGS ?= -shared
OPACITY_STRICT_FP_FLAGS ?= -ffp-contract=off
THERMAL_STRICT_FP_FLAGS ?= -ffp-contract=off
COMMON_LIBS ?= -ldl -pthread
CFITSIO_LIBS ?= -lcfitsio
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

SOLVER_TARGET := libxstar_solver.so
RATES_TARGET := libxstar_rates.so
MATRIX_TARGET := libxstar_matrix.so
EMISSIVITY_TARGET := libxstar_emissivity.so
OPACITY_TARGET := libxstar_opacity.so
THERMAL_TARGET := libxstar_thermal.so
FIXED_STATE_TARGET := libxstar_fixed_state.so
ENGINE_TARGET := libxstar_engine.so
API_TARGET := libxstar_api.so
CPP_BACKEND_TARGET := libxstar_backend_cpp.so
PYTHON_BACKEND_TARGET := libxstar_backend_python.so
EXECUTABLE_TARGET := xstar_cpp

PHYSICS_TARGETS := $(SOLVER_TARGET) $(RATES_TARGET) $(MATRIX_TARGET) \
	$(EMISSIVITY_TARGET) $(OPACITY_TARGET) $(THERMAL_TARGET) $(ENGINE_TARGET) $(FIXED_STATE_TARGET)
STANDALONE_TARGETS := $(API_TARGET) $(CPP_BACKEND_TARGET) $(PYTHON_BACKEND_TARGET) $(EXECUTABLE_TARGET)
TARGETS := $(PHYSICS_TARGETS) $(STANDALONE_TARGETS)

PUBLIC_HEADERS := xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_api.hpp xstar_element_engine.h xstar_spectral_engine.h xstar_thermal_engine.h xstar_fixed_state_engine.h
INTERNAL_HEADERS := xstar_standalone_internal.hpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp

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

$(ENGINE_TARGET): xstar_engine.cpp element_engine.cpp xstar_element_engine.h xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp $(SOLVER_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ xstar_engine.cpp element_engine.cpp -L. -lxstar_solver $(RPATH_ORIGIN)

$(FIXED_STATE_TARGET): fixed_state_engine.cpp xstar_fixed_state_engine.h xstar_element_engine.h xstar_spectral_engine.h $(ENGINE_TARGET) $(EMISSIVITY_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(THERMAL_STRICT_FP_FLAGS) $(SO_LDFLAGS) -o $@ fixed_state_engine.cpp -L. -lxstar_engine -lxstar_emissivity $(RPATH_ORIGIN)

$(API_TARGET): xstar_api.cpp compiled_case.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -DXSTAR_API_BUILD $(SO_LDFLAGS) \
		-o $@ xstar_api.cpp compiled_case.cpp $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(CPP_BACKEND_TARGET): xstar_backend_cpp.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp $(PHYSICS_TARGETS) $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) \
		-o $@ xstar_backend_cpp.cpp -L. -lxstar_api $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PYTHON_BACKEND_TARGET): xstar_backend_python.cpp xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_standalone_internal.hpp $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(PYTHON_INCLUDES) $(SO_LDFLAGS) \
		-o $@ xstar_backend_python.cpp -L. -lxstar_api $(PYTHON_LIBS) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(PYTHON_RPATHS) $(RPATH_ORIGIN)

$(EXECUTABLE_TARGET): xstar_standalone.cpp xstar_science_fits.cpp xstar_science_fits.hpp xstar_api.h xstar_api.hpp xstar_python_bridge.h xstar_fixed_state_engine.h xstar_thermal_engine.h $(API_TARGET) $(FIXED_STATE_TARGET) $(THERMAL_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ xstar_standalone.cpp xstar_science_fits.cpp \
		-L. -lxstar_api -lxstar_fixed_state -lxstar_thermal $(CFITSIO_LIBS) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

print-config:
	@echo CXX=$(CXX)
	@echo PYTHON_CONFIG=$(PYTHON_CONFIG)
	@echo PYTHON_INCLUDES=$(PYTHON_INCLUDES)
	@echo PYTHON_LIBS=$(PYTHON_LIBS)
	@echo PYTHON_LIBDIRS=$(PYTHON_LIBDIRS)
	@echo PYTHON_RPATHS=$(PYTHON_RPATHS)
	@echo OPACITY_STRICT_FP_FLAGS=$(OPACITY_STRICT_FP_FLAGS)
	@echo THERMAL_STRICT_FP_FLAGS=$(THERMAL_STRICT_FP_FLAGS)
	@echo FILESYSTEM_LINK_MODE=$(FILESYSTEM_LINK_MODE)
	@echo FILESYSTEM_LIBS=$(FILESYSTEM_LIBS)

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
	./$(EXECUTABLE_TARGET) fixed-state-self-test --case-dir ../../benchmarks/v06485_active_family_phase2_fixture
	./$(EXECUTABLE_TARGET) fixed-state-batch-self-test --case-dir ../../benchmarks/v06485_active_family_phase2_fixture --batch 4
	rm -rf .v06485_native_output
	./$(EXECUTABLE_TARGET) run-fixed-state --case-dir ../../benchmarks/v06485_active_family_phase2_fixture --output-dir .v06485_native_output
	test -s .v06485_native_output/xout_step.log
	test -s .v06485_native_output/xout_native_state.fits
	test -s .v06485_native_output/visited_records.csv
	rm -rf .v06485_native_output
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) self-test --backend python --plugin-dir . --python-path ../../.. --batch 4
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) python-bridge-test --plugin-dir . --python-path ../../..

install: all
	@echo "v0.6.48.5.3 keeps headers, C++ sources, shared libraries, executable, and Makefile in:"
	@pwd

clean:
	rm -f $(TARGETS) *.o
