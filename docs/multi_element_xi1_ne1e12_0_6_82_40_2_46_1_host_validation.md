# 0.6.82.40.2.46.1 multi-element_xi1_ne1e12 host validation

This is a **single C++ broad run** against the supplied existing FORTRAN XSTAR 2.59g reference. Do not rerun FORTRAN.

## 1. Build

```bash
heainit
make -C src/xstar_tools/xstar/cpp clean
make -C src/xstar_tools/xstar/cpp -j2 xstar-cpp
./src/xstar_tools/xstar/cpp/xstar-cpp --version
```

Required version:

```text
0.6.82.40.2.46.1
```

## 2. Static/preflight check

Run the preflight against the attached FORTRAN archive:

```bash
python3 tools/qualification/check_multi_element_xi1_ne1e12_0_6_82_40_2_46_1.py \
  --package "$PWD" \
  --fortran-reference ../fortran_multi_element_xi1_ne1e12.tar.gz
```

If you also keep an untouched original `.46.1` extraction under a distinct directory name, add for example:

```text
--baseline-package ../xstar_tools-0.6.82.40.2.46.1-original
```

to re-check byte identity of all C/C++ `.cpp/.hpp/.h` production sources. This identity has already been verified for the prepared artifact.

Required:

```text
MULTI_ELEMENT_XI1_NE1E12_CHECK_0682402461_RESULT=ACCEPT
```

## 3. Run one C++ broad case

```bash
python3 tools/qualification/run_multi_element_xi1_ne1e12_host_0_6_82_40_2_46_1.py \
  --package "$PWD" \
  --data-dir ../xstar/data \
  --fortran-reference ../fortran_multi_element_xi1_ne1e12.tar.gz \
  --output-root "$PWD/run_multi_element_xi1_ne1e12_0682402461" \
  --replace
```

The runner extracts/verifies the supplied FORTRAN archive but **does not execute FORTRAN**.

## Required broad science/path result

```text
MULTI_ELEMENT_XI1_NE1E12_0682402461_ORACLE_REFERENCE=ACCEPT
MULTI_ELEMENT_XI1_NE1E12_0682402461_CPP_RUNS=1
MULTI_ELEMENT_XI1_NE1E12_0682402461_FORTRAN_RERUN=NO
MULTI_ELEMENT_XI1_NE1E12_0682402461_SCIENCE_FITS_PAYLOAD=EXACT
MULTI_ELEMENT_XI1_NE1E12_0682402461_SCIENCE_STEP=EXACT
MULTI_ELEMENT_XI1_NE1E12_0682402461_SCIENCE=ACCEPT
MULTI_ELEMENT_XI1_NE1E12_0682402461_PATH=ACCEPT
MULTI_ELEMENT_XI1_NE1E12_0682402461_RESULT=ACCEPT
```

The runner also reports:

```text
CPP / FORTRAN internal-time ratio
CPP / FORTRAN wall-time ratio
CPP / FORTRAN peak-RSS ratio
BROAD_SPEED_VS_FORTRAN=ACCEPT|REJECT
RSS_GATE=MEASURED_ONLY
```

`BROAD_SPEED_VS_FORTRAN` is an important performance result but does not retroactively redefine the already explicit maintainer acceptance of `.46.1`. Peak RSS is measured and compared to the FORTRAN reference; no new arbitrary RSS promotion threshold is introduced.
