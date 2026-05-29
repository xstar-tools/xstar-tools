CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -fPIC -Wall -Wextra
LDFLAGS ?= -shared

TARGET := libxstar_solver.so
SRC := level_population.cpp
# Runtime package directory used by xstar_atomic.source_port.solver_backend.
# This Makefile lives under src/xstar_atomic/source_port/cpp/xstar_solver.
# Keep a copy beside solver_backend.py so PYTHONPATH=src runs can load it,
# while also leaving the local build artifact in this directory.
DESTDIR ?= ../..
DEST := $(DESTDIR)/$(TARGET)

.PHONY: all clean install runtime-copy

all: $(TARGET) runtime-copy

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) -o $@ $<

runtime-copy: $(TARGET)
	mkdir -p $(DESTDIR)
	cp $(TARGET) $(DEST)

install: runtime-copy

clean:
	rm -f $(TARGET) $(DEST)
