# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: phintfo.f90 / phint53.f90 / phint53hunt.f90 / phextrap.f90 / milne.f90 / enxt.f90
#   Role: Photoionization/recombination integration helpers called by ucalc data-type branches.
#   Relation: Source-faithful leaf translations; one-based search, threshold, and integration ranges are preserved.
#   Concordance: ION-001; MATRIX-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   Appendix A examples: Types 49 and 53 are tabulated partial photoionization cross sections; Type 59 is
#   an analytic partial cross section; Types 85/88 are K-shell/damped photoionization forms. The data type
#   chooses the cross-section representation, independently of downstream rate type.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Ionization/population runtime facade.
"""
