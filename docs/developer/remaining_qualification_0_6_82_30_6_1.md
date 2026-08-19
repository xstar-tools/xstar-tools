# 0.6.82.30.6.1 remaining qualification gate

This is a qualification-only revision. It does not alter production science.

It intentionally runs only 11 cases that were not executed by the earlier final gates:

- six spectrum/spectun cases: pow, bbody, bremss, file/spectun 0, 1, and 2;
- three ncn2 cases: 999, 9999, and 19999;
- two density-envelope C5 cases: density 1 and 1e12.

It does **not** rerun already accepted cfrac/emult, niter, lcpres, radexp, npass=3/5, C5 reference/low-xi, O, or Ca evidence. It also defers npass=1, Fe, the multi-element mixture, and output-control cases until after this 11-case run.

The runner continues after individual science rejections so all 11 cases receive a status in a single host execution.
