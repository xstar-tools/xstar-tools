# 0.6.48.10.0 accelerated-Python C++ binemis promotion

The accepted 0.6.48.9.5.1 accelerated-Python reference spends 254.812423 s in `final_product_build.spectrum.binemis_profile_seconds`, inside the final product writer after zone calculations are complete. The accepted 0.6.48.9.7 standalone C++ implementation already contains the corresponding native writer kernel.

0.6.48.10.0 changes only backend policy in `output_writers.py`: explicit accelerated C++ selection automatically makes the native `binemis` result the final spectrum product. The numerical native kernel (`cpp/line_emissivity.cpp`) and ctypes bridge (`cpp_backend_emissivity.py`) remain byte-for-byte source-identical to 0.6.48.9.7. Pure Python remains unpromoted.

Environment controls:

- `XSTAR_V064810_FORCE_PYTHON_BINEMIS=1` — force the historical Python final product loop.
- `XSTAR_V064810_ALLOW_PYTHON_BINEMIS_FALLBACK=1` — permit an explicitly requested C++ product to fall back to Python if the library fails. Default accelerated behavior is fail-closed so a missing library cannot silently restore a ~255 s writer cost.
- Historical explicit `XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP` / `...PRODUCT_CPP` controls remain supported.

Host acceptance:

- all eight FITS products other than `xout_spect1.fits` are data-payload exact against the accepted accelerated-Python reference;
- scientific `xout_step.log` content is unchanged after removing version/timing footer lines;
- `xout_spect1` has zero >1% cells against FORTRAN, pure Python, accelerated Python, and accepted standalone C++;
- timing footer proves automatic C++ product promotion with no fallback;
- report actual `binemis_profile_seconds` and speedup from the frozen 254.812423 s reference.
