# 0.6.85.1 — STANDALONE_OUTPUT_DIRECTORY_COEXISTENCE

## Purpose

`0.6.85` passed frozen parallel qualification but failed the first real-host four-job run because the scheduler creates `xstar-cpp.stdout.log` inside each job directory before launching `xstar-cpp`. The standalone production guard treated that unrelated file as a forbidden artifact, rejected the run, deleted otherwise valid XSTAR products, and returned code 20.

`0.6.85.1` changes output-directory ownership without changing XSTAR science.

## Contract

Allowed to coexist with XSTAR output:

- pre-existing unrelated files;
- `xstar-cpp.stdout.log`;
- scheduler logs;
- user notes;
- provenance files;
- any other non-XSTAR file.

Still required:

- required XSTAR products must be produced;
- missing/incomplete required products still fail;
- genuine science/runtime/publication failures still fail;
- failure remains visible through a nonzero return code and terminal/log diagnostics.

Removed:

- rejection merely because an unrelated file exists in the output directory;
- deletion of valid/partial XSTAR products merely because an unrelated file exists;
- failure-triggered deletion of XSTAR products.

The ownership rule is now:

> `xstar-cpp` owns and validates its own required products. It does not own the containing directory, and a failed run is non-destructive.

## Failure forensics

On standalone production failure, partial or invalid products are retained. The terminal stream reports:

```text
V048746255172582_FAILURE_PRODUCTS_PRESERVED=YES
V048746255172582_PRODUCTS_AUTODELETED=0
V048746255172582_RESULT=REJECT_STANDALONE_PRODUCTION_FAILURE
```

The reported retained FITS/STEP presence reflects what remains on disk after failure.

## XSTAR2XSPEC restart safety

Because failed products are now intentionally retained, file existence alone is no longer a sufficient restart-completion predicate. Each successful job receives:

```text
xstar-cpp.success
```

`--restart` reuses a job only when all of these exist:

```text
xout_spect1.fits
xout_step.log
xstar-cpp.success
```

Before a fresh job launch only the non-product success marker is invalidated. Existing XSTAR products are left in place for inspection until the solver overwrites them.

## Cleanup policy

`xstar2xspec-work/` is preserved by default, including after successful runs. `--save` remains accepted for compatibility but is no longer needed to preserve products.

Destructive cleanup is available only by explicit operator request after a fully successful run:

```bash
xstar-xspec ... --cleanup-work
```

No failed run invokes this cleanup path.

## Scientific boundary

This patch does not alter XSTAR scientific arithmetic, controller decisions, traversal/accumulation ordering, xstinitable grid semantics, or xstar2table transforms. The accepted `.85` scientific/planner/table lineage remains frozen.
## Formal host closure

The unchanged four-job `.85` host model was rerun with `.85.1` using two workers and returned:

```text
PARALLEL_NATIVE_XSTAR2XSPEC_06851_HOST_RESULT=ACCEPT
```

The first pass executed 4/4 jobs with `WORKERS_EFFECTIVE=2` and `MAX_ACTIVE=2`. The restart pass executed 0 jobs and reused 4/4 successful jobs. `0.6.85.1` is therefore formally accepted.

The acceptance runner originally created `scheduler-note.log`, `unrelated.txt`, and `user_note.txt` as explicit coexistence probes. The normal host runner no longer creates those artificial files; dedicated frozen qualification retains unrelated-file coverage.
