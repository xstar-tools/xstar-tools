CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra
LDFLAGS ?= -shared

SOLVER_TARGET := libxstar_solver.so
RATES_TARGET := libxstar_rates.so
MATRIX_TARGET := libxstar_matrix.so
TARGETS := $(SOLVER_TARGET) $(RATES_TARGET) $(MATRIX_TARGET)

.PHONY: all clean install

all: $(TARGETS)

$(SOLVER_TARGET): level_population.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(RATES_TARGET): rate_kernels.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(MATRIX_TARGET): matrix_kernels.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

install: all
	@echo "Shared libraries are intentionally kept in this cpp/ directory."

clean:
	rm -f $(TARGETS)
