CXX ?= g++
PYTHON_CONFIG ?= python3-config
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra -Wpedantic
CPPFLAGS ?=
SO_LDFLAGS ?= -shared
COMMON_LIBS ?= -ldl -pthread
PYTHON_INCLUDES := $(shell $(PYTHON_CONFIG) --includes)
PYTHON_LIBS := $(shell $(PYTHON_CONFIG) --embed --ldflags)
RPATH_ORIGIN := -Wl,-rpath,'$$ORIGIN'

# GCC 8 and older expose C++17 std::filesystem through libstdc++fs.
# Newer libstdc++ versions provide it directly. Detect the required link mode
# once at make parse time; callers may override FILESYSTEM_LIBS explicitly.
ifeq ($(origin FILESYSTEM_LIBS), undefined)
FILESYSTEM_LINK_MODE := $(shell \
	tmp=$$(mktemp -d /tmp/xstar-fs-link.XXXXXX); \
	printf '%s\n' '#include <filesystem>' 'int main() { return std::filesystem::current_path().empty(); }' > $$tmp/test.cpp; \
	if $(CXX) $(CPPFLAGS) $(CXXFLAGS) $$tmp/test.cpp -o $$tmp/test >/dev/null 2>&1; then \
		printf '%s' builtin; \
	elif $(CXX) $(CPPFLAGS) $(CXXFLAGS) $$tmp/test.cpp -o $$tmp/test -lstdc++fs >/dev/null 2>&1; then \
		printf '%s' stdc++fs; \
	else \
		printf '%s' unavailable; \
	fi; \
	rm -rf $$tmp)
ifeq ($(FILESYSTEM_LINK_MODE),stdc++fs)
FILESYSTEM_LIBS := -lstdc++fs
else ifeq ($(FILESYSTEM_LINK_MODE),builtin)
FILESYSTEM_LIBS :=
else
$(error C++17 std::filesystem link test failed; use a compatible compiler or set FILESYSTEM_LIBS explicitly)
endif
else
FILESYSTEM_LINK_MODE := override
endif

SOLVER_TARGET := libxstar_solver.so
RATES_TARGET := libxstar_rates.so
MATRIX_TARGET := libxstar_matrix.so
EMISSIVITY_TARGET := libxstar_emissivity.so
OPACITY_TARGET := libxstar_opacity.so
THERMAL_TARGET := libxstar_thermal.so
ENGINE_TARGET := libxstar_engine.so
API_TARGET := libxstar_api.so
CPP_BACKEND_TARGET := libxstar_backend_cpp.so
PYTHON_BACKEND_TARGET := libxstar_backend_python.so
EXECUTABLE_TARGET := xstar_cpp

PHYSICS_TARGETS := $(SOLVER_TARGET) $(RATES_TARGET) $(MATRIX_TARGET) \
	$(EMISSIVITY_TARGET) $(OPACITY_TARGET) $(THERMAL_TARGET) $(ENGINE_TARGET)
STANDALONE_TARGETS := $(API_TARGET) $(CPP_BACKEND_TARGET) $(PYTHON_BACKEND_TARGET) $(EXECUTABLE_TARGET)
TARGETS := $(PHYSICS_TARGETS) $(STANDALONE_TARGETS)

PUBLIC_HEADERS := xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_api.hpp
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

$(EMISSIVITY_TARGET): line_emissivity.cpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ $<

$(OPACITY_TARGET): opacity_kernels.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ opacity_kernels.cpp

$(THERMAL_TARGET): thermal_kernels.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ thermal_kernels.cpp

$(ENGINE_TARGET): xstar_engine.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) -o $@ xstar_engine.cpp

$(API_TARGET): xstar_api.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -DXSTAR_API_BUILD $(SO_LDFLAGS) \
		-o $@ xstar_api.cpp $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(CPP_BACKEND_TARGET): xstar_backend_cpp.cpp xstar_api.h xstar_backend_plugin.h xstar_standalone_internal.hpp $(PHYSICS_TARGETS) $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(SO_LDFLAGS) \
		-o $@ xstar_backend_cpp.cpp -L. -lxstar_api $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(PYTHON_BACKEND_TARGET): xstar_backend_python.cpp xstar_api.h xstar_backend_plugin.h xstar_python_bridge.h xstar_standalone_internal.hpp $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(PYTHON_INCLUDES) $(SO_LDFLAGS) \
		-o $@ xstar_backend_python.cpp -L. -lxstar_api $(PYTHON_LIBS) $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

$(EXECUTABLE_TARGET): xstar_standalone.cpp xstar_api.h xstar_api.hpp xstar_python_bridge.h $(API_TARGET)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ xstar_standalone.cpp \
		-L. -lxstar_api $(COMMON_LIBS) $(FILESYSTEM_LIBS) $(RPATH_ORIGIN)

print-config:
	@echo CXX=$(CXX)
	@echo PYTHON_CONFIG=$(PYTHON_CONFIG)
	@echo PYTHON_INCLUDES=$(PYTHON_INCLUDES)
	@echo PYTHON_LIBS=$(PYTHON_LIBS)
	@echo FILESYSTEM_LINK_MODE=$(FILESYSTEM_LINK_MODE)
	@echo FILESYSTEM_LIBS=$(FILESYSTEM_LIBS)

# These are ABI/scaffold tests only. They deliberately do not claim science parity.
test: all
	./$(EXECUTABLE_TARGET) list-backends
	./$(EXECUTABLE_TARGET) backend-info --backend cpp --plugin-dir .
	./$(EXECUTABLE_TARGET) self-test --backend cpp --plugin-dir . --batch 4
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) self-test --backend python --plugin-dir . --python-path ../../.. --batch 4
	PYTHONPATH=../../.. ./$(EXECUTABLE_TARGET) python-bridge-test --plugin-dir . --python-path ../../..

install: all
	@echo "v0.6.44.1 keeps headers, C++ sources, shared libraries, executable, and Makefile in:"
	@pwd

clean:
	rm -f $(TARGETS) *.o
