// xstar_tools 0.6.82.23: stock XSTAR 2.59g xstar.par contract.
#ifndef XSTAR_PARAMETER_CONTRACT_HPP
#define XSTAR_PARAMETER_CONTRACT_HPP
#include <array>
#include <cmath>
#include <stdexcept>
#include <string>
namespace xstar_parameter_contract {
enum class ParameterKind { Real, Integer, String };
struct Rule { const char* name; ParameterKind kind; const char* default_text; bool has_min; double minimum; bool has_max; double maximum; };
inline constexpr std::array<Rule, 59> kRules = {{
    {"cfrac", ParameterKind::Real, "0.0", true, 0.0, true, 1.0},
    {"temperature", ParameterKind::Real, "400.0", true, 0.0, true, 10000.0},
    {"lcpres", ParameterKind::Integer, "0", true, 0.0, true, 1.0},
    {"pressure", ParameterKind::Real, "0.03", true, 0.0, true, 1.0},
    {"density", ParameterKind::Real, "10000.0", true, 0.0, true, 1e+21},
    {"spectrum", ParameterKind::String, "pow", false, 0.0, false, 0.0},
    {"spectrum_file", ParameterKind::String, "spct.dat", false, 0.0, false, 0.0},
    {"spectun", ParameterKind::Integer, "0", true, 0.0, true, 2.0},
    {"trad", ParameterKind::Real, "-1.0", false, 0.0, false, 0.0},
    {"rlrad38", ParameterKind::Real, "1e-06", true, 0.0, true, 10000000000.0},
    {"column", ParameterKind::Real, "1e+17", true, 0.0, true, 1e+25},
    {"rlogxi", ParameterKind::Real, "5.0", true, -10.0, true, 10.0},
    {"abundtbl", ParameterKind::String, "xdef", false, 0.0, false, 0.0},
    {"habund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"heabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"liabund", ParameterKind::Real, "0.0", true, 0.0, true, 100.0},
    {"beabund", ParameterKind::Real, "0.0", true, 0.0, true, 100.0},
    {"babund", ParameterKind::Real, "0.0", true, 0.0, true, 100.0},
    {"cabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"nabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"oabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"fabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"neabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"naabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"mgabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"alabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"siabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"pabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"sabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"clabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"arabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"kabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"caabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"scabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"tiabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"vabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"crabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"mnabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"feabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"coabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"niabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"cuabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"znabund", ParameterKind::Real, "1.0", true, 0.0, true, 100.0},
    {"modelname", ParameterKind::String, "XSTAR Default", false, 0.0, false, 0.0},
    {"nsteps", ParameterKind::Integer, "3", true, 1.0, true, 1000.0},
    {"niter", ParameterKind::Integer, "0", false, 0.0, false, 0.0},
    {"lwrite", ParameterKind::Integer, "0", true, 0.0, true, 1.0},
    {"lprint", ParameterKind::Integer, "0", true, -1.0, true, 6.0},
    {"lstep", ParameterKind::Integer, "0", false, 0.0, false, 0.0},
    {"emult", ParameterKind::Real, "0.5", true, 1e-06, true, 1000000.0},
    {"taumax", ParameterKind::Real, "5.0", true, 1.0, true, 10000.0},
    {"xeemin", ParameterKind::Real, "0.1", true, 1e-06, true, 0.5},
    {"critf", ParameterKind::Real, "1e-07", true, 1e-24, true, 0.1},
    {"vturbi", ParameterKind::Real, "1.0", true, 0.0, true, 30000.0},
    {"radexp", ParameterKind::Real, "0.0", true, -3.0, true, 3.0},
    {"ncn2", ParameterKind::Integer, "9999", true, 999.0, true, 999999.0},
    {"loopcontrol", ParameterKind::Integer, "0", true, 0.0, true, 30000.0},
    {"npass", ParameterKind::Integer, "1", true, 1.0, true, 10000.0},
    {"mode", ParameterKind::String, "ql", false, 0.0, false, 0.0}
}};
inline const Rule* find(const std::string& name) { for (const auto& r:kRules) if(name==r.name) return &r; return nullptr; }
inline double numeric_default(const std::string& name) { const auto* r=find(name); if(!r || r->kind==ParameterKind::String) throw std::runtime_error("no numeric XSTAR default for "+name); return std::stod(r->default_text); }
inline std::string string_default(const std::string& name) { const auto* r=find(name); if(!r || r->kind!=ParameterKind::String) throw std::runtime_error("no string XSTAR default for "+name); return r->default_text; }
inline void validate_numeric(const Rule& r,double value) {
    if(!std::isfinite(value)) throw std::runtime_error(std::string(r.name)+" must be finite");
    if(r.kind==ParameterKind::Integer && value!=std::trunc(value)) throw std::runtime_error(std::string(r.name)+" must be an integer");
    const bool source_density_table_sentinel =
        std::string(r.name) == "radexp" && value < -99.0;
    if(r.has_min && value<r.minimum && !source_density_table_sentinel)
        throw std::runtime_error(std::string(r.name)+" below stock XSTAR minimum");
    if(r.has_max && value>r.maximum) throw std::runtime_error(std::string(r.name)+" above stock XSTAR maximum");
}
inline void validate_text(const std::string& name,const std::string& text) {
    const auto* r=find(name); if(!r) throw std::runtime_error("unknown XSTAR parameter: "+name);
    if(r->kind==ParameterKind::String) return;
    std::size_t used=0; double value=0.0; try { value=std::stod(text,&used); } catch(...) { throw std::runtime_error(name+" is not numeric"); }
    if(used!=text.size()) throw std::runtime_error(name+" has trailing nonnumeric text");
    validate_numeric(*r,value);
}
inline void validate_if_present(const std::string& name,double value) { const auto* r=find(name); if(r && r->kind!=ParameterKind::String) validate_numeric(*r,value); }
} // namespace
#endif
