CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra
LDFLAGS ?= -shared

DESTDIR ?= ..
SOLVER_TARGET := libxstar_solver.so
RATES_TARGET := libxstar_rates.so
TARGETS := $(SOLVER_TARGET) $(RATES_TARGET)

.PHONY: all clean install runtime-copy

all: $(TARGETS) runtime-copy

$(SOLVER_TARGET): level_population.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

$(RATES_TARGET): rate_kernels.cpp
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

runtime-copy: $(TARGETS)
	mkdir -p $(DESTDIR)
	cp $(SOLVER_TARGET) $(DESTDIR)/$(SOLVER_TARGET)
	cp $(RATES_TARGET) $(DESTDIR)/$(RATES_TARGET)

install: runtime-copy

clean:
	rm -f $(TARGETS) $(DESTDIR)/$(SOLVER_TARGET) $(DESTDIR)/$(RATES_TARGET)
