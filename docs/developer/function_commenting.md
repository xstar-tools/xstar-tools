# Function-level source comments

`xstar_tools 0.6.73` adds a reversible documentation overlay to the active
Python and C++ XSTAR implementation.  The goal is that a maintainer can open a
function and understand its local responsibility, physical role, inputs/outputs
in context, and source basis without first reconstructing the parity campaign
or opening the literature.

## Source hierarchy

Comments follow the same authority hierarchy as the parity freeze:

1. accepted qualification evidence for behavior already closed;
2. canonical XSTAR Fortran executable semantics;
3. the XSTAR manual and papers for physical explanation and context.

The literature therefore explains *why* an operation exists and what physical
process it represents; it does not override a qualified Fortran behavior.

## Reference set reviewed for this pass

Every page of the supplied reference bundle was rendered/reviewed and its text
indexed before the source pass.  The bundle contains:

- *XSTAR Manual* (`xstarmanual.pdf`), especially sections 11.4-11.7, chapter 12,
  and chapter 14;
- Kallman et al. (1996), *Photoionization Equilibrium Modeling of Iron L Line
  Emission*;
- Kallman & Bautista (2001), *Photoionization and High-Density Gas*;
- Bautista & Kallman (2001), *The XSTAR Atomic Database*;
- Kallman et al. (2004), *Photoionization Modeling and the K Lines of Iron*;
- Mendoza et al. (2021), *The XSTAR Atomic Database*.

The reviewed archive SHA-256 is
`a66718cf3b3d831906ed640c3bb9a2d8e81ac3bcdbfd4878d09fc680e6616e84`.

## What the comments explain

Scientific functions identify the relevant process and where it sits in the
XSTAR algorithm.  In particular, comments distinguish:

- preliminary ionization/recombination balance from the detailed multilevel
  statistical-equilibrium solve;
- level/superlevel/LTE and detailed-balance handling;
- heating/cooling terms and the thermal-equilibrium update;
- radiative/collisional rate evaluation from matrix consumption;
- bound-bound line emission/opacity and Type-50 profile/rebin work;
- bound-free photoionization/recombination-continuum work and Milne-related
  inverse rates;
- radial transfer, DSEC, state retention, and terminal publication;
- ATDB **data type** (how a record is interpreted/evaluated) versus **rate type**
  (how the evaluated quantity is consumed by XSTAR);
- K-vacancy/Auger/fluorescence paths where the 2004 Fe-K paper is applicable;
- final FITS/STEP publication versus the science that produced the values.

Implementation-only helpers are labeled as such.  ABI, parsing, serialization,
statistics, and diagnostic functions do not receive invented physical
citations.

## Reversible overlay

Function comments are bracketed by:

```text
XSTAR-FUNCTION-COMMENT-BEGIN
...
XSTAR-FUNCTION-COMMENT-END
```

The qualification checker removes only these blocks and requires exact
`0.6.72` source bytes underneath.  Python additionally requires AST equality;
C++ translation units must remain warning-clean under the project compile
settings.  This makes the comments useful documentation without silently
changing the accepted scientific implementation.

## Maintenance rule

New scientific functions should include a concise explanation of:

- the physical or algorithmic quantity being computed;
- how the function fits into the XSTAR workflow;
- the units/normalization or ordering invariant when it is not obvious;
- the relevant Fortran routine/data type/rate type when known;
- the manual/paper context when it genuinely applies.

Do not paste long derivations or debugging history into production code.  Link
such material from the developer/science guides instead.
