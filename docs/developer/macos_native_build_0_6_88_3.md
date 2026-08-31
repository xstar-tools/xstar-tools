# macOS native build — 0.6.88.3

`0.6.88.3` adds a qualified native macOS build path without modifying XSTAR science.

Prerequisites with Homebrew:

```bash
brew install cfitsio pkg-config
```

Build and inspect the selected configuration:

```bash
cd src/xstar_tools/xstar/cpp
make PLATFORM=macos print-config
make -j4 PLATFORM=macos
```

The default compiler is Apple `clang++` unless `CXX` is explicitly overridden. Shared libraries
use `.dylib`, `-dynamiclib`, `@rpath/libxstar_*.dylib` install names, and `@loader_path` runtime
search paths. CFITSIO is discovered first with `pkg-config`; if that fails on macOS the Makefile
uses `brew --prefix cfitsio` to derive include/lib paths.

Run the native host qualification from the package root:

```bash
python3 tools/qualification/run_macos_native_build_host_0_6_88_3.py \
  --package "$PWD" \
  --predecessor ../xstar_tools-0.6.88.2.2 \
  --output-root "$PWD/run_macos_native_build_06883_host" \
  --jobs 4
```

The runner must be executed on Darwin and requires Apple Clang. MPI is outside this release's
macOS acceptance scope and remains opt-in.
