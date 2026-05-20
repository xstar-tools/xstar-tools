# Hydrogen v0.4.36 correction targets

This immutable diagnostic inventory records the bounded H I differences exposed
by the v0.4.35 H/He/O call-73 all-element probe. Captured values do not enter
production rates, matrices, populations, or corrections.

The four omitted source records are data type 62, rate type 3, with packed
endpoint pairs `1<->4`, `1<->7`, `1<->8`, and `1<->9`. Each accepted record
must create four matrix terms, restoring 16 terms. The production rerun must
also validate all 718 H/He/O initial compact populations and end with
`all_element_pre_continuum_acceptance_ready=True`.
