CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra
LDFLAGS ?= -shared

SOLVER_TARGET := libxstar_solver.so
RATES_TARGET := libxstar_rates.so
MATRIX_TARGET := libxstar_matrix.so
EMISSIVITY_TARGET := libxstar_emissivity.so
OPACITY_TARGET := libxstar_opacity.so
THERMAL_TARGET := libxstar_thermal.so
ENGINE_TARGET := libxstar_engine.so
TARGETS := $(SOLVER_TARGET) $(RATES_TARGET) $(MATRIX_TARGET) $(EMISSIVITY_TARGET) $(OPACITY_TARGET) $(THERMAL_TARGET) $(ENGINE_TARGET)

.PHONY: all clean install

all: $(TARGETS)

$(SOLVER_TARGET): level_population.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(RATES_TARGET): rate_kernels.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(MATRIX_TARGET): matrix_kernels.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(EMISSIVITY_TARGET): line_emissivity.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(OPACITY_TARGET): opacity_kernels.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ opacity_kernels.cpp

$(THERMAL_TARGET): thermal_kernels.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ thermal_kernels.cpp

$(ENGINE_TARGET): xstar_engine.cpp xstar_backend_common.hpp compact_arrays.hpp error_codes.hpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ xstar_engine.cpp

install: all
	@echo "Shared libraries are intentionally kept in this cpp/ directory."

clean:
	rm -f $(TARGETS)
