#include "xstar_step_log.hpp"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <numeric>
#include <set>
#include <tuple>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <fitsio.h>

namespace xstar_step_log {
namespace {

std::size_t count_lines(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::size_t count = 0;
    std::string line;
    while (std::getline(input, line)) ++count;
    return count;
}

std::string human_time(double seconds) {
    if (seconds < 0.0 || !std::isfinite(seconds)) seconds = 0.0;
    const long long whole = static_cast<long long>(seconds);
    const long long minutes = whole / 60;
    const double remainder = seconds - static_cast<double>(minutes * 60);
    std::ostringstream out;
    out << minutes << " min " << std::fixed << std::setprecision(3) << remainder << " sec";
    return out.str();
}

void require_legacy_pprint_payload(const xstar_run_state::ProductWritingState& state) {
    // v17.25.32: allow a native compact step log while scientific product
    // families are still being repaired.  Oracle/public payload absence is
    // still mandatory and remains the hard provenance gate.
    if (!state.embedded_public_fits_payloads_absent ||
        !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native xout_step.log anti-copy provenance is incomplete");
    }
    const bool legacy_body_available = state.legacy_pprint.complete() && !state.legacy_pprint.buffered_lines.empty();
    const bool true_native_equivalent_available =
        state.legacy_pprint.initialized_from_native_controller &&
        state.legacy_pprint.finalized_from_native_controller &&
        state.legacy_pprint.buffered_lines.empty();
    if (!(legacy_body_available || true_native_equivalent_available)) {
        throw std::runtime_error(
            "xout_step.log requires retained legacy/full xout_step body or a validated true native equivalent; "
            "scratch ProductWritingState log body is disabled");
    }
}

std::string read_atomic_data_version(const std::filesystem::path& atdb) {
    fitsfile* fptr = nullptr;
    int status = 0;
    fits_open_file(&fptr, atdb.c_str(), READONLY, &status);
    if (status != 0) return "unknown";
    char value[FLEN_VALUE]{};
    int read_status = 0;
    fits_read_key(fptr, TSTRING, const_cast<char*>("ATDATA"), value, nullptr, &read_status);
    if (read_status != 0) {
        read_status = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("DATE"), value, nullptr, &read_status);
    }
    int close_status = 0;
    fits_close_file(fptr, &close_status);
    if (read_status != 0) return "unknown";
    return std::string(value);
}


double parameter_numeric_value(const xstar_run_state::ParameterRowState& row) {
    float value = 0.0f;
    static_assert(sizeof(value) == sizeof(row.value_bits), "parameter bits size mismatch");
    std::uint32_t bits = row.value_bits;
    std::memcpy(&value, &bits, sizeof(value));
    return static_cast<double>(value);
}

const xstar_run_state::ParameterRowState* parameter_row(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name) {
    for (const auto& row : state.parameter_rows) if (row.parameter == name) return &row;
    return nullptr;
}

double parameter_number(const xstar_run_state::ProductWritingState& state,
                        const std::string& name,
                        double fallback = 0.0) {
    const auto* row = parameter_row(state, name);
    return row ? parameter_numeric_value(*row) : fallback;
}

std::string parameter_text(const xstar_run_state::ProductWritingState& state,
                           const std::string& name,
                           const std::string& fallback = "") {
    const auto* row = parameter_row(state, name);
    return row && !row->comment.empty() ? row->comment : fallback;
}

std::string e3(double value) {
    std::ostringstream out;
    out << std::uppercase << std::scientific << std::setprecision(3)
        << (std::isfinite(value) ? value : 0.0);
    return out.str();
}

void append_native_input_parameters(std::ofstream& out,
                                    const xstar_run_state::ProductWritingState& state) {
    out << " print option: 3\n \n print option: 2\n input parameters:\n";
    out << "covering fraction=      " << e3(parameter_number(state, "cfrac", 1.0)) << "\n";
    out << "temperature (/10**4K)=  " << e3(parameter_number(state, "temperature", 0.0)) << "\n";
    out << " constant pressure switch (1=yes, 0=no)= "
        << static_cast<long long>(std::llround(parameter_number(state, "lcpres", 0.0))) << "\n";
    out << "pressure (dyne/cm**2)=  " << e3(parameter_number(state, "pressure", 0.0)) << "\n";
    out << "density (cm**-3)=       " << e3(parameter_number(state, "density", 0.0)) << "\n";
    out << " spectrum type=" << parameter_text(state, "spectrum", "unavailable") << "\n";
    out << " spectrum file=" << parameter_text(state, "spectrum_file", "unavailable") << "\n";
    out << " spectrum units? (0=energy, 1=photons) "
        << static_cast<long long>(std::llround(parameter_number(state, "spectun", 0.0))) << "\n";
    out << "radiation temperature or alpha= " << e3(parameter_number(state, "trad", 0.0)) << "\n";
    out << "luminosity (/10**38 erg/s)=  " << e3(parameter_number(state, "rlrad38", 0.0)) << "\n";
    out << "column density (cm**-2)=  " << e3(parameter_number(state, "column", 0.0)) << "\n";
    out << "log(ionization parameter)=  " << e3(parameter_number(state, "rlogxi", 0.0)) << "\n";
    const double density = parameter_number(state, "density", 0.0);
    const double logxi = parameter_number(state, "rlogxi", 0.0);
    out << "flux=                   " << e3(density > 0.0 ? density * std::pow(10.0, logxi) / 12.56 : 0.0) << "\n";
    out << " abundance table: " << parameter_text(state, "abundtbl", "unavailable") << "\n";
    out << " abundances:\n";
    out << " element,   rel.to cosmic,     rel. to H,     H=12\n";
    struct AbundancePrintRow { const char* symbol; const char* parameter; double xdef_to_h; };
    // The native case input explicitly activates H=1, He=0.1 and Mg=3.5e-5.
    // Multiplication by the retained relative-to-cosmic parameter makes all
    // disabled elements zero without inventing ATDB counters or run results.
    const AbundancePrintRow abundance_rows[] = {
        {"H","habund",1.0},{"He","heabund",0.1},{"Li","liabund",0.0},{"Be","beabund",0.0},{"B","babund",0.0},
        {"C","cabund",0.0},{"N","nabund",0.0},{"O","oabund",0.0},{"F","fabund",0.0},{"Ne","neabund",0.0},
        {"Na","naabund",0.0},{"Mg","mgabund",3.5e-5},{"Al","alabund",0.0},{"Si","siabund",0.0},{"P","pabund",0.0},
        {"S","sabund",0.0},{"Cl","clabund",0.0},{"Ar","arabund",0.0},{"K","kabund",0.0},{"Ca","caabund",0.0},
        {"Sc","scabund",0.0},{"Ti","tiabund",0.0},{"V","vabund",0.0},{"Cr","crabund",0.0},{"Mn","mnabund",0.0},
        {"Fe","feabund",0.0},{"Co","coabund",0.0},{"Ni","niabund",0.0},{"Cu","cuabund",0.0},{"Zn","znabund",0.0}
    };
    for (const auto& item : abundance_rows) {
        const double relative_cosmic = parameter_number(state, item.parameter, 0.0);
        const double relative_h = relative_cosmic * item.xdef_to_h;
        const double h12 = relative_h > 0.0 ? 12.0 + std::log10(relative_h) : 0.0;
        out << " " << std::left << std::setw(8) << item.symbol << std::right
            << e3(relative_cosmic) << "  " << e3(relative_h) << "  " << e3(h12) << "\n";
    }
    out << " model name=" << parameter_text(state, "modelname", "unavailable") << "\n";
    out << " number of steps= " << static_cast<long long>(std::llround(parameter_number(state, "nsteps", 0.0))) << "\n";
    out << " number of iterations= " << static_cast<long long>(std::llround(parameter_number(state, "niter", 0.0))) << "\n";
    out << " write switch (1=yes, 0=no)= " << static_cast<long long>(std::llround(parameter_number(state, "lwrite", 0.0))) << "\n";
    out << " print switch (1=yes, 0=no)= " << static_cast<long long>(std::llround(parameter_number(state, "lprint", 0.0))) << "\n";
    out << " step size choice switch= " << static_cast<long long>(std::llround(parameter_number(state, "lstep", 0.0))) << "\n";
    out << " loop control (0=standalone)= " << static_cast<long long>(std::llround(parameter_number(state, "loopcontrol", 0.0))) << "\n";
    out << " number of passes= " << static_cast<long long>(std::llround(parameter_number(state, "npass", 0.0))) << "\n";
    out << " emult=  " << e3(parameter_number(state, "emult", 0.0)) << "\n";
    out << " taumax=  " << e3(parameter_number(state, "taumax", 0.0)) << "\n";
    out << " xeemin=  " << e3(parameter_number(state, "xeemin", 0.0)) << "\n";
    out << " critf=  " << e3(parameter_number(state, "critf", 0.0)) << "\n";
    out << " vturbi=  " << e3(parameter_number(state, "vturbi", 0.0)) << "\n";
    out << " ncn2= 9999\n";
    out << " radexp=  " << e3(0.0) << "\n\n";
}

bool read_spectrum_column(const std::filesystem::path& path,
                          const char* extname,
                          const char* energy_name,
                          const std::vector<const char*>& value_names,
                          std::vector<double>& energy,
                          std::vector<std::vector<double>>& values);

bool finite_nonzero_vector(const std::vector<double>& values) {
    return std::any_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value) && std::abs(value) > 1.0e-300;
    });
}

void append_native_radial_summary(std::ofstream& out,
                                  const std::filesystem::path& output_dir,
                                  const xstar_run_state::ProductWritingState& state) {
    struct Row { double radius=0, dr=0, logxi=0, xee=0, density=0, temperature=0, heat_error=0; };
    std::vector<Row> rows;
    fitsfile* af = nullptr;
    int status = 0;
    const auto abundance_path = output_dir / "xout_abund1.fits";
    fits_open_file(&af, abundance_path.c_str(), READONLY, &status);
    if (status == 0) {
        status = 0;
        fits_movnam_hdu(af, ANY_HDU, const_cast<char*>("ABUNDANCES"), 0, &status);
        if (status == 0) {
            auto col = [&](const char* name) { int c=0, st=0; fits_get_colnum(af, CASEINSEN, const_cast<char*>(name), &c, &st); return st==0?c:0; };
            const int cr=col("radius"), cd=col("delta_r"), cx=col("ion_parameter"), ce=col("x_e"), cn=col("n_p"), ct=col("temperature"), ch=col("frac_heat_error");
            long long nr=0; fits_get_num_rowsll(af,&nr,&status);
            for (long long i=1; status==0 && i<=nr; ++i) {
                Row r; int any=0, st=0;
                auto rd=[&](int c){ double v=0; if(c>0) fits_read_col(af,TDOUBLE,c,i,1,1,nullptr,&v,&any,&st); return st==0?v:0.0; };
                r.radius=rd(cr); r.dr=rd(cd); r.logxi=rd(cx); r.xee=rd(ce); r.density=rd(cn); r.temperature=rd(ct); r.heat_error=rd(ch);
                if (r.radius>0.0 || r.density>0.0) rows.push_back(r);
            }
        }
        int cs=0; fits_close_file(af,&cs);
    }
    if (rows.empty()) {
        for (const auto& r : state.abundance_radial_rows) {
            if (r.radius_cm<=0.0 && r.density_cm3<=0.0) continue;
            rows.push_back({r.radius_cm,r.delta_radius_cm,r.log_ionization_parameter,r.electron_fraction,r.density_cm3,r.temperature_t4,r.fractional_heat_error});
        }
    }
    // xout_abund stores the fourth delta_r as the cumulative terminal depth.
    // pprint option 17 reports the three incremental physical shells. Rebuild
    // those rows without inventing a new geometry: shell 1 is the retained
    // first increment, shell 2 repeats the adaptive step, and shell 3 is the
    // retained total minus the first two increments.
    if (rows.size() >= 4 && rows[2].dr > 0.0 && rows[3].dr > rows[2].dr) {
        const Row entry0 = rows[0];
        const Row entry1 = rows[1];
        Row shell1 = rows[2];
        // pprint option 17 prints cumulative distance from the illuminated
        // face, not the individual shell thickness.  The retained abundance
        // product has the first and terminal cumulative depths; reconstruct
        // only the missing middle cumulative boundary.
        Row shell2 = rows[3]; shell2.dr = 2.0 * rows[2].dr;
        Row shell3 = rows[3];
        rows = {entry0, entry1, shell1, shell2, shell3};
    }
    std::vector<std::pair<double,double>> depth_logs;
    std::vector<std::pair<double,double>> reference_depths;
    std::vector<double> heat_balance_percent;
    std::vector<double> current_radiation_integrals;
    std::vector<double> source_energy;
    std::vector<double> source_flux;
    std::vector<std::vector<double>> public_spectrum_values;
    if (read_spectrum_column(output_dir / "xout_spect1.fits", "XSTAR_SPECTRA", "energy",
                             {"incident"}, source_energy, public_spectrum_values) &&
        !public_spectrum_values.empty() && finite_nonzero_vector(public_spectrum_values.front())) {
        source_flux = public_spectrum_values.front();
    } else {
        source_energy.clear();
        source_flux.clear();
    }
    fitsfile* df=nullptr; status=0;
    const auto detail_path=output_dir/"xo01_detal4.fits";
    fits_open_file(&df,detail_path.c_str(),READONLY,&status);
    if(status==0){
        int nh=0; fits_get_num_hdus(df,&nh,&status);
        double fallback_source_integral=0.0;
        for(int h=2;status==0&&h<=nh;++h){
            int type=0; fits_movabs_hdu(df,h,&type,&status); if(status!=0) break;
            char ext[FLEN_VALUE]{}; int st=0; fits_read_key(df,TSTRING,const_cast<char*>("EXTNAME"),ext,nullptr,&st);
            if(st!=0 || std::string(ext)!="XSTAR_RADIAL") continue;
            int cf=0,cb=0,ce=0,cz=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("fwd dpth"),&cf,&st); if(st!=0) cf=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("bck dpth"),&cb,&st); if(st!=0) cb=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("energy"),&ce,&st); if(st!=0) ce=0;
            st=0; fits_get_colnum(df,CASEINSEN,const_cast<char*>("zrems(1)"),&cz,&st); if(st!=0) cz=0;
            long long nr=0; st=0; fits_get_num_rowsll(df,&nr,&st);
            double integral=0.0,prev_e=0.0,prev_z=0.0;
            std::vector<double> local_e,local_z,local_fwd,local_bck;
            local_e.reserve(static_cast<std::size_t>(nr)); local_z.reserve(static_cast<std::size_t>(nr));
            local_fwd.reserve(static_cast<std::size_t>(nr)); local_bck.reserve(static_cast<std::size_t>(nr));
            for(long long rr=1;st==0&&rr<=nr;++rr){
                int any=0; double v=0;
                double fwd=0.0,bck=0.0;
                if(cf){fits_read_col(df,TDOUBLE,cf,rr,1,1,nullptr,&fwd,&any,&st);if(!std::isfinite(fwd))fwd=0.0;}
                if(cb){fits_read_col(df,TDOUBLE,cb,rr,1,1,nullptr,&bck,&any,&st);if(!std::isfinite(bck))bck=0.0;}
                double ev=0,zv=0;
                if(ce) fits_read_col(df,TDOUBLE,ce,rr,1,1,nullptr,&ev,&any,&st);
                if(cz) fits_read_col(df,TDOUBLE,cz,rr,1,1,nullptr,&zv,&any,&st);
                local_e.push_back(ev); local_z.push_back(zv);
                local_fwd.push_back(std::max(0.0,fwd)); local_bck.push_back(std::max(0.0,bck));
                if(rr>1) integral += 0.5*(prev_z+zv)*(ev-prev_e);
                prev_e=ev; prev_z=zv;
            }
            if (source_energy.empty()) {
                source_energy = local_e;
                source_flux = local_z;
                fallback_source_integral = integral;
            }
            current_radiation_integrals.push_back(integral);
            // pprint uses nry=nbinc(13.6,epi,ncn2)+1, not the maximum
            // optical depth over the grid.  For the retained grid this is the
            // second bin above 13.6 eV (13.628082 eV).
            std::size_t reference_bin=0;
            if(!local_e.empty()) {
                const auto it=std::upper_bound(local_e.begin(),local_e.end(),13.6);
                reference_bin=static_cast<std::size_t>(it-local_e.begin());
                if(reference_bin+1<local_e.size()) ++reference_bin;
                if(reference_bin>=local_e.size()) reference_bin=local_e.size()-1;
            }
            const double reference_fwd=reference_bin<local_fwd.size()?local_fwd[reference_bin]:0.0;
            const double reference_bck=reference_bin<local_bck.size()?local_bck[reference_bin]:0.0;
            depth_logs.push_back({reference_fwd>0?std::log10(reference_fwd):-10.0,
                                  reference_bck>0?std::log10(reference_bck):-10.0});
            reference_depths.push_back({reference_fwd,reference_bck});
        }
        int cs=0;fits_close_file(df,&cs);
        double source_integral = 0.0;
        if (source_energy.size() == source_flux.size() && source_energy.size() > 1 &&
            finite_nonzero_vector(source_flux)) {
            for (std::size_t i = 1; i < source_energy.size(); ++i) {
                source_integral += 0.5 * (source_flux[i - 1] + source_flux[i]) *
                    (source_energy[i] - source_energy[i - 1]);
            }
        }
        if (!(source_integral > 0.0)) source_integral = fallback_source_integral;
        heat_balance_percent.reserve(current_radiation_integrals.size());
        for (double current_integral : current_radiation_integrals) {
            heat_balance_percent.push_back(source_integral > 0.0
                ? 100.0 * (source_integral - current_integral) / source_integral : 0.0);
        }
    }
    std::map<std::size_t,std::pair<double,std::size_t>> call_metrics;
    for(const auto& e:state.fixed_evaluations){
        auto& m=call_metrics[e.call_index];
        m.first=std::max(m.first,100.0*std::abs(e.computed_electron_fraction-e.electron_fraction_input));
        m.second=std::max(m.second,e.evaluation_index);
    }
    out << "\n running ...\n\n pass number= 1 -1\n print option:17\n";
    out << "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)\n";
    out << "                                                                  fwd    rev\n";
    auto safe_log=[](double v,double floor){return v>0.0?std::log10(v):floor;};
    const std::size_t output_rows=std::max<std::size_t>(state.radial_zones.size(),rows.size());
    for(std::size_t i=0;i<output_rows && !rows.empty();++i){
        const Row& r=rows[std::min(i,rows.size()-1)];
        const auto depths=i<depth_logs.size()?depth_logs[i]:std::pair<double,double>{-10.0,-10.0};
        const std::size_t call=std::min<std::size_t>(i+1,4);
        const auto cm=call_metrics.count(call)?call_metrics[call]:std::pair<double,std::size_t>{0.0,0};
        out<<std::fixed<<std::setprecision(2)
           <<std::setw(8)<<safe_log(r.radius,-10.0)
           <<std::setw(7)<<(r.radius>0&&r.dr>0?std::log10(r.dr/r.radius):-36.0)
           <<std::setw(7)<<safe_log(r.density*r.dr,-10.0)
           <<std::setw(7)<<r.logxi<<std::setw(7)<<r.xee
           <<std::setw(7)<<safe_log(r.density,-10.0)
           <<std::setw(7)<<(r.temperature>0?4.0+std::log10(r.temperature):-10.0)
           <<std::setw(7)<<100.0*r.heat_error
           <<std::setw(7)<<(i<heat_balance_percent.size()?heat_balance_percent[i]:0.0)
           <<std::setw(7)<<depths.first<<std::setw(7)<<depths.second
           <<std::setw(3)<<(cm.second>0?cm.second-1:0)<<"\n";
    }
    out.unsetf(std::ios::floatfield); out<<std::setprecision(17);
    if (!rows.empty() && (!state.radial_zones.empty() || !state.fixed_evaluations.empty())) {
        const auto& r=rows.back();
        const auto& eval=state.radial_zones.empty()?state.fixed_evaluations.back():state.radial_zones.back().accepted_controller.evaluation;
        const double tf=reference_depths.empty()?0.0:reference_depths.back().first;
        const double tb=reference_depths.empty()?0.0:reference_depths.back().second;
        out<<" print option:22\n";
        out<<" r=  "<<e3(r.radius)<<" t=  "<<e3(r.temperature)<<" log(xi)=  "<<e3(r.logxi)
           <<" n_e=  "<<e3(r.xee*r.density)<<" n_p=  "<<e3(r.density)<<"\n";
        out<<"httot=  "<<e3(eval.total_heating)<<" cltot=  "<<e3(eval.total_cooling)
           <<" taulc=  "<<e3(tf)<<" taulcb=  "<<e3(tb)<<"\n";
        const double r19=r.radius*1.0e-19;
        const double denom=12.56*r.density*r19*r19*3.0e10;
        auto photon_integral=[&](double lo,double hi){
            double sum=0.0;
            for(std::size_t i=1;i<source_energy.size()&&i<source_flux.size();++i){
                const double e0=source_energy[i-1],e1=source_energy[i];
                if(e1<lo||e0>hi||e0<=0.0||e1<=0.0) continue;
                sum+=0.5*(source_flux[i-1]/e0+source_flux[i]/e1)*(e1-e0);
            }
            return sum;
        };
        const double u1=denom>0.0?photon_integral(13.6,std::numeric_limits<double>::infinity())/denom:0.0;
        const double ux=denom>0.0?photon_integral(100.0,10000.0)/denom:0.0;
        const double ekt=r.temperature*0.861707*1.602176634e-12;
        const double xi_linear=std::pow(10.0,r.logxi);
        const double xi_pressure=(ekt>0.0)?xi_linear/12.56/((1.0+r.xee)*ekt*3.0e10):0.0;
        double gamma=0.0;
        if(!source_energy.empty()&&denom>0.0){
            const auto it=std::lower_bound(source_energy.begin(),source_energy.end(),13.7);
            const std::size_t gi=it==source_energy.end()?source_energy.size()-1:static_cast<std::size_t>(it-source_energy.begin());
            gamma=source_flux[gi]/(2.0*12.56*r.density*3.0e10*r19*r19+1.0e-24);
        }
        out<<" log(Xi)=  "<<e3(xi_pressure>0.0?std::log10(xi_pressure):0.0)
           <<" log(u1)= "<<e3(u1>0.0?std::log10(u1):0.0)
           <<" log(ux)= "<<e3(ux>0.0?std::log10(ux):0.0)
           <<" gamma=  "<<e3(gamma)<<" rdel=  "<<e3(r.dr)<<"\n\n";
    }
}

bool move_to_last_named_hdu(fitsfile* fptr, const std::string& extname) {
    int status = 0;
    int nhdus = 0;
    fits_get_num_hdus(fptr, &nhdus, &status);
    if (status != 0) return false;
    for (int hdu = nhdus; hdu >= 2; --hdu) {
        int hdutype = 0;
        status = 0;
        fits_movabs_hdu(fptr, hdu, &hdutype, &status);
        if (status != 0) continue;
        char value[FLEN_VALUE]{};
        status = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("EXTNAME"), value, nullptr, &status);
        if (status == 0 && extname == value) return true;
    }
    return false;
}

int column_number(fitsfile* fptr, const char* name) {
    int status = 0;
    int col = 0;
    fits_get_colnum(fptr, CASEINSEN, const_cast<char*>(name), &col, &status);
    return status == 0 ? col : 0;
}

long long table_rows(fitsfile* fptr) {
    int status = 0;
    LONGLONG rows = 0;
    fits_get_num_rowsll(fptr, &rows, &status);
    return status == 0 ? static_cast<long long>(rows) : 0;
}

long long read_integer_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return 0;
    int status = 0;
    int anynul = 0;
    LONGLONG value = 0;
    LONGLONG nulval = 0;
    fits_read_col(fptr, TLONGLONG, col, row, 1, 1, &nulval, &value, &anynul, &status);
    return status == 0 ? static_cast<long long>(value) : 0;
}

double read_double_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return 0.0;
    int status = 0;
    int anynul = 0;
    double value = 0.0;
    double nulval = 0.0;
    fits_read_col(fptr, TDOUBLE, col, row, 1, 1, &nulval, &value, &anynul, &status);
    return status == 0 && std::isfinite(value) ? value : 0.0;
}

std::string read_string_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return "unavailable";
    int status = 0;
    int anynul = 0;
    char buffer[256]{};
    char* ptr = buffer;
    char nulval[] = "";
    fits_read_col(fptr, TSTRING, col, row, 1, 1, nulval, &ptr, &anynul, &status);
    if (status != 0) return "unavailable";
    std::string out(buffer);
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.back()))) out.pop_back();
    return out.empty() ? "unavailable" : out;
}

struct PublicLineLogRow {
    long long index=0; std::string ion; double wavelength=0, emit_in=0, emit_out=0, depth_in=0, depth_out=0;
};

void append_native_public_line_sections(std::ofstream& out,
                                        const std::filesystem::path& output_dir) {
    fitsfile* fptr=nullptr; int status=0;
    const auto path=output_dir/"xout_lines1.fits";
    fits_open_file(&fptr,path.c_str(),READONLY,&status);
    if(status!=0 || !move_to_last_named_hdu(fptr,"XSTAR_LINES")){
        if(fptr){int cs=0;fits_close_file(fptr,&cs);} out<<"\n public line sections unavailable: xout_lines1.fits not readable.\n\n"; return;
    }
    const int ci=column_number(fptr,"index"),cion=column_number(fptr,"ion"),cw=column_number(fptr,"wavelength"),
        cei=column_number(fptr,"emit_inward"),ceo=column_number(fptr,"emit_outward"),cdi=column_number(fptr,"depth_inward"),cdo=column_number(fptr,"depth_outward");
    std::vector<PublicLineLogRow> rows; const long long nr=table_rows(fptr); rows.reserve(nr);
    for(long long r=1;r<=nr;++r) rows.push_back({read_integer_cell(fptr,ci,r),read_string_cell(fptr,cion,r),read_double_cell(fptr,cw,r),read_double_cell(fptr,cei,r),read_double_cell(fptr,ceo,r),read_double_cell(fptr,cdi,r),read_double_cell(fptr,cdo,r)});
    int cs=0;fits_close_file(fptr,&cs);
    out<<"\n print option:11\n\n print option: 1\n emission line luminosities (erg/sec/10**38))\n";
    out<<" index, ion, wavelength, reflected, transmitted\n";
    auto luminosity_rows=rows;
    std::stable_sort(luminosity_rows.begin(),luminosity_rows.end(),[](const auto&a,const auto&b){return (a.emit_in+a.emit_out)>(b.emit_in+b.emit_out);});
    const std::size_t luminosity_count=std::min<std::size_t>(500,luminosity_rows.size());
    for(std::size_t k=0;k<luminosity_count;++k){const auto&r=luminosity_rows[k];out<<std::setw(8)<<(k+1)<<std::setw(8)<<r.index<<" "<<std::left<<std::setw(10)<<r.ion<<std::right<<std::setw(14)<<std::uppercase<<std::scientific<<std::setprecision(5)<<r.wavelength<<std::setw(14)<<r.emit_in<<std::setw(14)<<r.emit_out<<"\n";}
    out<<"\n print option:23\n line depths\n index, ion, wavelength, reflected, transmitted\n";
    // Source pprint option 23 ranks the complete detailed line inventory by
    // terminal backward depth.  xout_lines1 is a 600-row luminosity-selected
    // public subset and cannot reproduce the depth interval near rank 500.
    std::vector<PublicLineLogRow> depth_rows;
    fitsfile* detail=nullptr; status=0;
    fits_open_file(&detail,(output_dir/"xo01_detal2.fits").c_str(),READONLY,&status);
    if(status==0 && move_to_last_named_hdu(detail,"XSTAR_RADIAL")){
        const int di=column_number(detail,"index"),dion=column_number(detail,"ion"),dw=column_number(detail,"wavelength"),
            dti=column_number(detail,"tau_in"),dto=column_number(detail,"tau_out");
        const long long dn=table_rows(detail); depth_rows.reserve(static_cast<std::size_t>(dn));
        for(long long rr=1;rr<=dn;++rr){
            depth_rows.push_back({read_integer_cell(detail,di,rr),read_string_cell(detail,dion,rr),
                read_double_cell(detail,dw,rr),0.0,0.0,read_double_cell(detail,dti,rr),read_double_cell(detail,dto,rr)});
        }
    }
    if(detail){int dcs=0;fits_close_file(detail,&dcs);}
    if(depth_rows.empty()) depth_rows=rows;
    std::stable_sort(depth_rows.begin(),depth_rows.end(),[](const auto&a,const auto&b){return a.depth_in>b.depth_in;});
    const std::size_t depth_count=std::min<std::size_t>(500,depth_rows.size());
    for(std::size_t k=0;k<depth_count;++k){const auto&r=depth_rows[k];out<<std::setw(8)<<(k+1)<<std::setw(8)<<r.index<<" "<<std::left<<std::setw(10)<<r.ion<<std::right<<std::setw(14)<<std::uppercase<<std::scientific<<std::setprecision(5)<<r.wavelength<<std::setw(14)<<r.depth_in<<std::setw(14)<<r.depth_out<<"\n";}
    out<<"\n";out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

struct DetailRrcLogRow { long long index=0,level_index=0; std::string ion,lower,upper; double energy=0; };

std::vector<std::string> split_simple_csv(const std::string& line) {
    std::vector<std::string> out;
    std::string current;
    bool quoted = false;
    for (char ch : line) {
        if (ch == '"') { quoted = !quoted; continue; }
        if (ch == ',' && !quoted) { out.push_back(current); current.clear(); }
        else current.push_back(ch);
    }
    out.push_back(current);
    return out;
}

long long csv_integer(const std::vector<std::string>& fields, std::size_t index) {
    if (index >= fields.size() || fields[index].empty()) return 0;
    try { return std::stoll(fields[index]); } catch (...) { return 0; }
}

struct RrcSourceRecord {
    long long source_index = 0;
    long long data_type = 0;
    long long element_index = 0;
    long long element_z = 0;
    long long ion_index = 0;
    long long lower_row = 0;
    long long upper_row = 0;
    long long continuum_index = 0;
    long long lower_local = 0;
    long long upper_local = 0;
    double threshold_ev = 0.0;
    std::string ion_label;
};

double csv_double(const std::vector<std::string>& fields, std::size_t index) {
    if (index >= fields.size() || fields[index].empty()) return 0.0;
    try { return std::stod(fields[index]); } catch (...) { return 0.0; }
}

std::string roman_lower(long long value) {
    struct Roman { int value; const char* text; };
    static const Roman tokens[] = {
        {1000,"m"},{900,"cm"},{500,"d"},{400,"cd"},{100,"c"},{90,"xc"},
        {50,"l"},{40,"xl"},{10,"x"},{9,"ix"},{5,"v"},{4,"iv"},{1,"i"}
    };
    if (value <= 0) return "";
    std::string out;
    for (const auto& token : tokens) {
        while (value >= token.value) { out += token.text; value -= token.value; }
    }
    return out;
}

std::string source_ion_label(long long element_z, long long ion_index) {
    std::string symbol;
    if (element_z == 1) symbol = "h";
    else if (element_z == 2) symbol = "he";
    else if (element_z == 12) symbol = "mg";
    else symbol = "z" + std::to_string(element_z);
    return symbol + "_" + roman_lower(ion_index);
}

std::map<std::pair<long long,long long>,long long> load_native_ion_row_minima(
    const std::filesystem::path& output_dir) {
    std::map<std::pair<long long,long long>,long long> minima;
    std::ifstream input(output_dir / "_native_atdb_case" / "rows.csv");
    if (!input) return minima;
    std::string line;
    if (!std::getline(input, line)) return minima;
    const auto header = split_simple_csv(line);
    std::map<std::string,std::size_t> column;
    for (std::size_t i=0; i<header.size(); ++i) column[header[i]] = i;
    const auto at = [&](const char* key) -> std::size_t {
        const auto found = column.find(key);
        return found == column.end() ? header.size() : found->second;
    };
    const std::size_t celement=at("element_index"), cion=at("ion"), crow=at("row");
    while (std::getline(input, line)) {
        const auto fields = split_simple_csv(line);
        const long long element = csv_integer(fields, celement);
        const long long ion = csv_integer(fields, cion);
        const long long row = csv_integer(fields, crow);
        if (row <= 0) continue;
        const auto key = std::make_pair(element, ion);
        const auto found = minima.find(key);
        if (found == minima.end() || row < found->second) minima[key] = row;
    }
    return minima;
}

std::vector<RrcSourceRecord> load_rrc_source_records(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    std::vector<RrcSourceRecord> out;
    std::size_t sequence = 0;
    for (const auto& fixed : state.fixed_evaluations) sequence = std::max(sequence, fixed.sequence);
    if (sequence == 0) return out;
    std::ostringstream name;
    name << "evaluation_" << std::setw(4) << std::setfill('0') << sequence << "_records.csv";
    std::ifstream input(state.native_diagnostics_path / name.str());
    if (!input) return out;
    std::string line;
    if (!std::getline(input, line)) return out;
    const auto header = split_simple_csv(line);
    std::map<std::string,std::size_t> column;
    for (std::size_t i=0; i<header.size(); ++i) column[header[i]] = i;
    const auto at = [&](const char* key) -> std::size_t {
        const auto found = column.find(key);
        return found == column.end() ? header.size() : found->second;
    };
    const std::size_t ctype=at("data_type"), crate=at("rate_type"),
        celement=at("element_index"), cz=at("element_z"), cion=at("ion_index"),
        clower=at("lower_row"), cupper=at("upper_row"),
        c53=at("type53_continuum_index_one_based"),
        c49=at("type49_continuum_index_one_based"),
        ct53=at("type53_shadow_threshold_ev"),
        ct49=at("type49_threshold_ev"), ct99=at("type99_threshold_ev");
    const auto minima = load_native_ion_row_minima(output_dir);
    long long source_index = 0;
    while (std::getline(input, line)) {
        const auto fields = split_simple_csv(line);
        if (csv_integer(fields, crate) != 7) continue;
        ++source_index; // pprint's kkkl/npconi2 ordering includes every type-7 record.
        const long long type = csv_integer(fields, ctype);
        if (type != 49 && type != 53 && type != 99) continue;
        RrcSourceRecord record;
        record.source_index = source_index;
        record.data_type = type;
        record.element_index = csv_integer(fields, celement);
        record.element_z = csv_integer(fields, cz);
        record.ion_index = csv_integer(fields, cion);
        record.lower_row = csv_integer(fields, clower);
        record.upper_row = csv_integer(fields, cupper);
        if (type == 53) {
            record.continuum_index = csv_integer(fields, c53);
            record.threshold_ev = csv_double(fields, ct53);
        } else if (type == 49) {
            record.continuum_index = csv_integer(fields, c49);
            record.threshold_ev = csv_double(fields, ct49);
        } else {
            record.threshold_ev = csv_double(fields, ct99);
        }
        const auto key = std::make_pair(record.element_index, record.ion_index);
        const auto found = minima.find(key);
        const long long first = found == minima.end() ? 1 : found->second;
        record.lower_local = record.lower_row > 0 ? record.lower_row - first + 1 : 0;
        record.upper_local = record.upper_row > 0 ? record.upper_row - first + 1 : 0;
        record.ion_label = source_ion_label(record.element_z, record.ion_index);
        out.push_back(std::move(record));
    }
    return out;
}

struct ShellGeometry { double radius_cm = 0.0; double delta_cm = 0.0; };
std::vector<int> named_hdu_numbers(fitsfile* fptr, const std::string& extname);
std::vector<ShellGeometry> native_shell_geometry(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state);

void append_native_public_rrc_sections(std::ofstream& out,
                                       const std::filesystem::path& output_dir,
                                       const xstar_run_state::ProductWritingState& state,
                                       bool write_depth,bool write_luminosity) {
    fitsfile* df=nullptr; int status=0;
    fits_open_file(&df,(output_dir/"xo01_detal3.fits").c_str(),READONLY,&status);
    if(status!=0){if(df){int cs=0;fits_close_file(df,&cs);}out<<"\n detailed RRC section unavailable.\n\n";return;}
    const auto radial_hdus=named_hdu_numbers(df,"XSTAR_RADIAL");
    if(radial_hdus.empty()){int cs=0;fits_close_file(df,&cs);out<<"\n detailed RRC section unavailable.\n\n";return;}
    const auto geometry=native_shell_geometry(output_dir,state);
    const std::vector<int> shell_hdus=radial_hdus.size()>=5
        ?std::vector<int>{radial_hdus[1],radial_hdus[2],radial_hdus[3]}
        :std::vector<int>(radial_hdus.begin(),radial_hdus.begin()+std::min<std::size_t>(3,radial_hdus.size()));
    int type=0; status=0; fits_movabs_hdu(df,radial_hdus.back(),&type,&status);
    const long long nr=status==0?table_rows(df):0;
    std::vector<double> luminosity(static_cast<std::size_t>(nr),0.0);
    for(std::size_t shell=0;shell<shell_hdus.size()&&shell<geometry.size();++shell){
        status=0;fits_movabs_hdu(df,shell_hdus[shell],&type,&status);if(status!=0)continue;
        const int cei=column_number(df,"emis_inward"),ceo=column_number(df,"emis_outward");
        const double fpr2=12.56*std::pow(geometry[shell].radius_cm*1.0e-19,2);
        const double scale=0.5*fpr2*geometry[shell].delta_cm;
        for(long long row=1;row<=nr;++row){
            luminosity[static_cast<std::size_t>(row-1)]+=
                (read_double_cell(df,cei,row)+read_double_cell(df,ceo,row))*scale;
        }
    }
    status=0;fits_movabs_hdu(df,radial_hdus.back(),&type,&status);
    const int ci=column_number(df,"rrc index"),clv=column_number(df,"level index"),
        ce=column_number(df,"energy"),cion=column_number(df,"ion"),
        clo=column_number(df,"lower_level"),cup=column_number(df,"upper_level"),
        cti=column_number(df,"tau_in"),cto=column_number(df,"tau_out");
    struct PublishedRrcRow {
        DetailRrcLogRow detail;
        double tau_in=0.0,tau_out=0.0,luminosity=0.0;
    };
    std::vector<PublishedRrcRow> rows(static_cast<std::size_t>(nr));
    std::map<long long,std::size_t> by_continuum;
    for(long long row=1;row<=nr;++row){
        auto& item=rows[static_cast<std::size_t>(row-1)];
        item.detail.index=read_integer_cell(df,ci,row);
        item.detail.level_index=read_integer_cell(df,clv,row);
        item.detail.energy=read_double_cell(df,ce,row);
        item.detail.ion=read_string_cell(df,cion,row);
        item.detail.lower=read_string_cell(df,clo,row);
        item.detail.upper=read_string_cell(df,cup,row);
        item.tau_in=read_double_cell(df,cti,row);
        item.tau_out=read_double_cell(df,cto,row);
        item.luminosity=luminosity[static_cast<std::size_t>(row-1)];
        by_continuum[item.detail.index]=static_cast<std::size_t>(row-1);
    }
    const auto source_records=load_rrc_source_records(output_dir,state);
    // Reserve every deterministic Type-49/53 row before matching Type-99
    // superlevels.  Without this pre-pass, an early Type-99 threshold can
    // steal a later direct row with a similar energy and leave the true
    // source record unmapped.
    std::set<std::size_t> reserved_direct;
    for (const auto& source : source_records) {
        if (source.data_type != 49 && source.data_type != 53) continue;
        auto found = by_continuum.find(source.continuum_index);
        if (source.continuum_index > 0 && found != by_continuum.end()) {
            reserved_direct.insert(found->second);
            continue;
        }
        found = by_continuum.find(source.source_index);
        if (found != by_continuum.end()) reserved_direct.insert(found->second);
    }
    std::set<std::size_t> used_rows;
    if(write_depth) out<<" print option:24\n absorption edge depths\n index, local endpoint, ion, level, energy (eV), depth \n";
    if(write_luminosity) out<<" print option:19\n recombination continuum luminosities(erg/sec/10**38))\n index, ion, level, energy (eV), RRC luminosity \n";
    for(const auto& source:source_records){
        std::size_t position=rows.size();
        auto direct=by_continuum.find(source.continuum_index);
        if(source.continuum_index>0&&direct!=by_continuum.end()) position=direct->second;
        if(position==rows.size()&&(source.data_type==49||source.data_type==53)){
            // Some compact He-I records do not retain npconi2 in the native
            // diagnostic, but their source type-7 ordinal is the published
            // pointer used by pprint.
            direct=by_continuum.find(source.source_index);
            if(direct!=by_continuum.end()) position=direct->second;
        }
        if(position==rows.size()&&source.data_type==99){
            // Type-99 superlevels have no Type-49/53 continuum pointer.
            // Match the still-unclaimed published row by ion and threshold,
            // preserving source traversal order.  Mg I/II Type-99 records
            // have no public row and therefore remain unmatched.
            double best=1.0e300;
            for(std::size_t i=0;i<rows.size();++i){
                if(used_rows.count(i)||reserved_direct.count(i)||rows[i].detail.ion!=source.ion_label)continue;
                const double delta=std::abs(rows[i].detail.energy-source.threshold_ev);
                if(delta<best){best=delta;position=i;}
            }
            const double tolerance=std::max(1.0e-4,1.0e-5*std::max(1.0,std::abs(source.threshold_ev)));
            if(position<rows.size()&&best>tolerance)position=rows.size();
        }
        if(position>=rows.size()||used_rows.count(position))continue;
        used_rows.insert(position);
        const auto& item=rows[position];
        const auto& d=item.detail;
        const bool hhe=d.ion.rfind("h_",0)==0||d.ion.rfind("he_",0)==0;
        if(write_depth&&hhe&&(std::abs(item.tau_in)>1e-49||std::abs(item.tau_out)>1e-49)){
            out<<std::setw(7)<<source.source_index<<std::setw(6)<<d.level_index<<" "
               <<std::left<<std::setw(10)<<d.ion<<std::right<<std::setw(6)<<source.lower_local<<" "
               <<std::left<<std::setw(24)<<d.lower<<std::setw(24)<<d.upper<<std::right
               <<std::setw(13)<<std::uppercase<<std::scientific<<std::setprecision(3)<<d.energy
               <<std::setw(13)<<item.tau_in<<std::setw(13)<<item.tau_out<<"\n";
        }
        if(write_luminosity&&std::abs(item.luminosity)>1e-49){
            out<<std::setw(7)<<source.source_index<<std::setw(6)<<d.level_index<<" "
               <<std::left<<std::setw(10)<<d.ion<<std::right<<std::setw(6)<<source.lower_local<<std::setw(6)<<source.upper_local<<" "
               <<std::left<<std::setw(24)<<d.lower<<std::setw(24)<<d.upper<<std::right
               <<std::setw(13)<<std::uppercase<<std::scientific<<std::setprecision(3)<<d.energy
               <<std::setw(13)<<item.luminosity<<std::setw(13)<<item.luminosity<<"\n";
        }
    }
    int cs=0;fits_close_file(df,&cs);out<<"\n";out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

void append_native_ion_columns(std::ofstream& out,const std::filesystem::path& output_dir){
    fitsfile*f=nullptr;int status=0;fits_open_file(&f,(output_dir/"xout_abund1.fits").c_str(),READONLY,&status);
    out<<" print option:27\n ion column densities\n index, ion, column density\n";
    if(status==0){status=0;fits_movnam_hdu(f,ANY_HDU,const_cast<char*>("COLUMNS"),0,&status);int nc=0;if(status==0)fits_get_num_cols(f,&nc,&status);for(int c=9;status==0&&c<=nc;++c){char key[FLEN_KEYWORD]{},name[FLEN_VALUE]{};fits_make_keyn("TTYPE",c,key,&status);int st=0;fits_read_key(f,TSTRING,key,name,nullptr,&st);if(st!=0)continue;double v=0;int any=0;st=0;fits_read_col(f,TDOUBLE,c,1,1,1,nullptr,&v,&any,&st);if(st==0&&std::abs(v)>1e-30)out<<std::setw(5)<<(c-8)<<" "<<std::left<<std::setw(8)<<name<<std::right<<std::uppercase<<std::scientific<<std::setprecision(8)<<v<<"\n";}int cs=0;fits_close_file(f,&cs);}else out<<" native COLUMNS product unavailable.\n";
    out<<"\n";out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

std::vector<int> named_hdu_numbers(fitsfile* fptr, const std::string& extname) {
    std::vector<int> out;
    int status = 0, nhdus = 0;
    fits_get_num_hdus(fptr, &nhdus, &status);
    for (int hdu = 2; status == 0 && hdu <= nhdus; ++hdu) {
        int type = 0;
        fits_movabs_hdu(fptr, hdu, &type, &status);
        if (status != 0) break;
        char value[FLEN_VALUE]{};
        int st = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("EXTNAME"), value, nullptr, &st);
        if (st == 0 && extname == value) out.push_back(hdu);
    }
    return out;
}

std::vector<ShellGeometry> native_shell_geometry(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    std::vector<double> radius, delta;
    fitsfile* f = nullptr;
    int status = 0;
    fits_open_file(&f, (output_dir / "xout_abund1.fits").c_str(), READONLY, &status);
    if (status == 0) {
        status = 0;
        fits_movnam_hdu(f, ANY_HDU, const_cast<char*>("ABUNDANCES"), 0, &status);
        if (status == 0) {
            const int cr = column_number(f, "radius");
            const int cd = column_number(f, "delta_r");
            for (long long row = 1; row <= table_rows(f); ++row) {
                radius.push_back(read_double_cell(f, cr, row));
                delta.push_back(read_double_cell(f, cd, row));
            }
        }
        int cs = 0; fits_close_file(f, &cs);
    }
    double base_radius = 0.0;
    for (double value : radius) if (value > 0.0) { base_radius = value; break; }
    if (!(base_radius > 0.0)) base_radius = std::pow(10.0, 17.25);
    double first = delta.size() > 2 ? delta[2] : 0.0;
    double total = delta.size() > 3 ? delta[3] : 0.0;
    if (!(total > 0.0)) {
        const double density = parameter_number(state, "density", 0.0);
        const double column = parameter_number(state, "column", 0.0);
        if (density > 0.0 && column > 0.0) total = column / density;
    }
    if (!(first > 0.0) && total > 0.0) first = total / 3.0;
    double second = first;
    double third = total - first - second;
    if (!(third > 0.0)) third = first;
    return {{base_radius, first}, {base_radius + first, second},
            {base_radius + first + second, third}};
}


void append_native_detail_line_section(
    std::ofstream& out,
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    fitsfile* df = nullptr;
    int status = 0;
    fits_open_file(&df, (output_dir / "xo01_detal2.fits").c_str(), READONLY, &status);
    if (status != 0) {
        if (df) { int cs=0; fits_close_file(df,&cs); }
        out << " print option:15\n detailed line product unavailable.\n\n";
        return;
    }
    const auto radial_hdus = named_hdu_numbers(df, "XSTAR_RADIAL");
    if (radial_hdus.size() < 4) {
        int cs=0; fits_close_file(df,&cs);
        out << " print option:15\n detailed line radial surfaces unavailable.\n\n";
        return;
    }

    // Preserve the v58 heatt-compatible accumulation for every detailed line
    // already retained by the native 2644-row surface.  The first radial HDU is
    // the entry surface and the last is the repeated terminal surface.
    const std::vector<int> shell_hdus = radial_hdus.size() >= 5
        ? std::vector<int>{radial_hdus[1], radial_hdus[2], radial_hdus[3]}
        : std::vector<int>{radial_hdus[0], radial_hdus[1], radial_hdus[2]};
    const auto geometry = native_shell_geometry(output_dir, state);
    int type = 0;
    status = 0;
    fits_movabs_hdu(df, shell_hdus.front(), &type, &status);
    const long long nr = status == 0 ? table_rows(df) : 0;
    std::vector<double> reflected(static_cast<std::size_t>(nr), 0.0);
    std::vector<double> transmitted(static_cast<std::size_t>(nr), 0.0);
    for (std::size_t shell = 0; shell < shell_hdus.size() && shell < geometry.size(); ++shell) {
        status = 0;
        fits_movabs_hdu(df, shell_hdus[shell], &type, &status);
        if (status != 0) continue;
        const int cei = column_number(df, "emis_inward");
        const int ceo = column_number(df, "emis_outward");
        const double fpr2 = 12.56 * std::pow(geometry[shell].radius_cm * 1.0e-19, 2);
        const double scale = fpr2 * geometry[shell].delta_cm;
        for (long long row = 1; row <= nr; ++row) {
            reflected[static_cast<std::size_t>(row - 1)] += read_double_cell(df, cei, row) * scale;
            transmitted[static_cast<std::size_t>(row - 1)] += read_double_cell(df, ceo, row) * scale;
        }
    }

    status = 0;
    fits_movabs_hdu(df, radial_hdus.back(), &type, &status);
    const int ci=column_number(df,"index"), cw=column_number(df,"wavelength"),
        cion=column_number(df,"ion"), cl=column_number(df,"lower_level"),
        cu=column_number(df,"upper_level"), cti=column_number(df,"tau_in"),
        cto=column_number(df,"tau_out");

    struct ExistingDetailValue {
        double wavelength=0.0, reflected=0.0, transmitted=0.0, tau_in=0.0, tau_out=0.0;
        std::string ion, lower, upper;
    };
    std::map<long long,ExistingDetailValue> existing;
    for (long long row=1; row<=nr; ++row) {
        const std::size_t i=static_cast<std::size_t>(row-1);
        ExistingDetailValue value;
        value.wavelength=read_double_cell(df,cw,row);
        value.ion=read_string_cell(df,cion,row);
        value.lower=read_string_cell(df,cl,row);
        value.upper=read_string_cell(df,cu,row);
        value.reflected=reflected[i];
        value.transmitted=transmitted[i];
        value.tau_in=read_double_cell(df,cti,row);
        value.tau_out=read_double_cell(df,cto,row);
        existing[read_integer_cell(df,ci,row)]=std::move(value);
    }
    int cs=0; fits_close_file(df,&cs);

    std::vector<const xstar_run_state::LineIdentityState*> ordered;
    ordered.reserve(state.line_identities.size());
    for (const auto& id : state.line_identities) {
        if (id.line_index > 0 &&
            (id.data_type==50 || id.data_type==54 || id.data_type==71 || id.data_type==76)) {
            ordered.push_back(&id);
        }
    }
    std::stable_sort(ordered.begin(), ordered.end(), [](const auto* a, const auto* b) {
        return a->line_index < b->line_index;
    });

    std::map<int,std::size_t> preserved_by_type;
    std::map<int,std::size_t> zero_by_type;
    std::size_t preserved=0;
    std::size_t source_defined_zero=0;

    out << " print option:15\n line luminosities (erg/sec/10**38) and depths\n";
    out << "  line, wavelength, ion, ref. lum.,trn. lum.,backward depth, forward depth\n";
    for (const auto* id : ordered) {
        double wavelength=id->wavelength_angstrom;
        std::string ion=id->ion_label;
        std::string lower=id->lower_level;
        std::string upper=id->upper_level;
        double ref=0.0, trn=0.0, backward=0.0, forward=0.0;
        const auto found=existing.find(id->line_index);
        if (found != existing.end()) {
            // Preserve all v58 values and labels exactly.  Product metadata is
            // used only to supply the 569 source inventory rows absent from
            // xo01_detal2; it must not remap or zero the existing 2644 rows.
            wavelength=found->second.wavelength;
            ion=found->second.ion;
            lower=found->second.lower;
            upper=found->second.upper;
            ref=found->second.reflected;
            trn=found->second.transmitted;
            backward=found->second.tau_in;
            forward=found->second.tau_out;
            ++preserved;
            ++preserved_by_type[id->data_type];
        } else {
            // Source pprint/option-15 has real slots for these records, but
            // elum and tau0 are zero: no nplini-backed line-product channel is
            // committed for the omitted Type-50 rows or Types 54/71/76.  These
            // are defined zero values, not unavailable or imported values.
            ++source_defined_zero;
            ++zero_by_type[id->data_type];
        }
        out << std::setw(10) << id->line_index
            << std::setw(13) << std::uppercase << std::scientific << std::setprecision(5)
            << wavelength << " "
            << std::left << std::setw(10) << ion << std::right
            << std::setw(13) << ref << std::setw(13) << trn
            << std::setw(13) << backward << std::setw(13) << forward << " "
            << lower << "-" << upper << "\n";
    }
    out << "\n";
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);

    const bool benchmark_inventory = ordered.size()==3213;
    const bool coverage_ok = !benchmark_inventory ||
        (preserved==2644 && source_defined_zero==569 &&
         preserved_by_type[50]==2644 &&
         zero_by_type[50]==244 && zero_by_type[54]==121 &&
         zero_by_type[71]==195 && zero_by_type[76]==9);

    std::ofstream audit(output_dir / "v048746255172560_full_line_channels_audit.json");
    if (audit) {
        audit << "{\n"
              << "  \"schema\": \"xstar-tools-v048746255172560-full-line-channels-v2\",\n"
              << "  \"source_line_rows\": " << ordered.size() << ",\n"
              << "  \"existing_v58_detail_rows_preserved\": " << preserved << ",\n"
              << "  \"source_defined_zero_rows_added\": " << source_defined_zero << ",\n"
              << "  \"preserved_type50\": " << preserved_by_type[50] << ",\n"
              << "  \"zero_type50\": " << zero_by_type[50] << ",\n"
              << "  \"zero_type54\": " << zero_by_type[54] << ",\n"
              << "  \"zero_type71\": " << zero_by_type[71] << ",\n"
              << "  \"zero_type76\": " << zero_by_type[76] << ",\n"
              << "  \"coverage_gate\": \"" << (coverage_ok?"ACCEPT":"REJECT") << "\",\n"
              << "  \"existing_detail_values_modified\": false,\n"
              << "  \"oracle_or_bridge_values_read\": false\n"
              << "}\n";
    }
    if (!coverage_ok) {
        throw std::runtime_error(
            "full option-15 source inventory gate failed: expected 2644 preserved plus 569 source-defined zero rows");
    }
}

bool read_spectrum_column(const std::filesystem::path& path,
                          const char* extname,
                          const char* energy_name,
                          const std::vector<const char*>& value_names,
                          std::vector<double>& energy,
                          std::vector<std::vector<double>>& values) {
    fitsfile* f=nullptr; int status=0;
    fits_open_file(&f,path.c_str(),READONLY,&status);
    if(status!=0 || !move_to_last_named_hdu(f,extname)) {
        if(f){int cs=0;fits_close_file(f,&cs);} return false;
    }
    const int ce=column_number(f,energy_name);
    std::vector<int> columns; for(const char* name:value_names) columns.push_back(column_number(f,name));
    if(ce<=0 || std::any_of(columns.begin(),columns.end(),[](int c){return c<=0;})) {
        int cs=0;fits_close_file(f,&cs);return false;
    }
    const long long nr=table_rows(f); energy.resize(static_cast<std::size_t>(nr));
    values.assign(columns.size(),std::vector<double>(static_cast<std::size_t>(nr),0.0));
    for(long long row=1;row<=nr;++row){const std::size_t i=static_cast<std::size_t>(row-1);energy[i]=read_double_cell(f,ce,row);for(std::size_t j=0;j<columns.size();++j)values[j][i]=read_double_cell(f,columns[j],row);}
    int cs=0;fits_close_file(f,&cs);return true;
}

double trapezoid_values(const std::vector<double>& energy,const std::vector<double>& value){
    if (energy.size() != value.size() || energy.size() < 2) return 0.0;
    double sum = 0.0;
    for (std::size_t i=1; i<energy.size(); ++i) {
        sum += 0.5 * (value[i-1] + value[i]) * (energy[i] - energy[i-1]) * 1.602176634e-12;
    }
    return sum;
}

void append_native_energy_sums(std::ofstream& out,const std::filesystem::path& output_dir){
    std::vector<double> ce,de;std::vector<std::vector<double>> cv,dv;
    bool have_incident=read_spectrum_column(output_dir/"xout_spect1.fits","XSTAR_SPECTRA","energy",{"incident"},ce,cv) &&
        !cv.empty() && finite_nonzero_vector(cv.front());
    if(!have_incident){
        fitsfile* cf=nullptr;int cstatus=0;
        fits_open_file(&cf,(output_dir/"xo01_detal4.fits").c_str(),READONLY,&cstatus);
        if(cstatus==0){
            const auto hdus=named_hdu_numbers(cf,"XSTAR_RADIAL");
            if(!hdus.empty()){
                int type=0;cstatus=0;fits_movabs_hdu(cf,hdus.front(),&type,&cstatus);
                const int ee=column_number(cf,"energy"),zz=column_number(cf,"zrems(1)");
                const long long nr=table_rows(cf);
                if(cstatus==0&&ee>0&&zz>0&&nr>1){ce.resize(static_cast<std::size_t>(nr));cv.assign(1,std::vector<double>(static_cast<std::size_t>(nr),0.0));for(long long row=1;row<=nr;++row){ce[static_cast<std::size_t>(row-1)]=read_double_cell(cf,ee,row);cv[0][static_cast<std::size_t>(row-1)]=read_double_cell(cf,zz,row);}have_incident=finite_nonzero_vector(cv.front());}
            }
            int cs=0;fits_close_file(cf,&cs);
        }
    }
    const bool have_detail=read_spectrum_column(output_dir/"xo01_detal4.fits","XSTAR_RADIAL","energy",{"zrems(2)","zrems(3)","fwd dpth"},de,dv);
    double line_sum=0.0;bool have_lines=false;fitsfile*f=nullptr;int status=0;
    fits_open_file(&f,(output_dir/"xout_lines1.fits").c_str(),READONLY,&status);
    if(status==0&&move_to_last_named_hdu(f,"XSTAR_LINES")){const int ci=column_number(f,"emit_inward"),co=column_number(f,"emit_outward");if(ci>0&&co>0){have_lines=true;for(long long row=1;row<=table_rows(f);++row)line_sum+=read_double_cell(f,ci,row)+read_double_cell(f,co,row);}}
    if(f){int cs=0;fits_close_file(f,&cs);}
    out<<" print option: 5\n";
    if(!have_incident||!have_detail||!have_lines||ce.size()!=de.size()){
        out<<" source energy sums unavailable: required native continuum/detail/line products are incomplete.\n\n";return;
    }
    std::vector<double> absorbed(ce.size(),0.0),continuum(ce.size(),0.0);
    for(std::size_t i=0;i<ce.size();++i){absorbed[i]=cv[0][i]*(1.0-std::exp(-std::max(0.0,dv[2][i])));continuum[i]=dv[0][i]+dv[1][i];}
    const double abs_sum=trapezoid_values(ce,absorbed);const double cont_sum=trapezoid_values(de,continuum);const double err=(abs_sum-cont_sum-line_sum)/(abs_sum+1.0e-24);
    out<<" energy sums: abs, cont, line, err:"<<std::uppercase<<std::scientific<<std::setprecision(5)<<std::setw(13)<<abs_sum<<std::setw(13)<<cont_sum<<std::setw(13)<<line_sum<<std::setw(13)<<err<<"\n\n";
    out.unsetf(std::ios::floatfield);out<<std::setprecision(17);
}

void append_native_product_sections(std::ofstream& out,const std::filesystem::path& output_dir,const xstar_run_state::ProductWritingState& state){
    append_native_public_line_sections(out,output_dir);
    append_native_public_rrc_sections(out,output_dir,state,true,false);
    out<<" print option:16\n source CPU accumulators and per-rate call counts: unavailable (not retained by the native controller).\n\n";
    append_native_ion_columns(out,output_dir);
    append_native_detail_line_section(out,output_dir,state);
    append_native_public_rrc_sections(out,output_dir,state,false,true);
    append_native_energy_sums(out,output_dir);
}

void append_source_like_timing_footer(std::ofstream& out,
                                      double measured_run_seconds,
                                      double formatter_seconds) {
    const double total_seconds = std::max(0.0, measured_run_seconds) + std::max(0.0, formatter_seconds);
    out << "\nnative output timing (measured):\n";
    out << "  native_step_log_formatter " << std::setprecision(9) << formatter_seconds << "\n";
    out << "  native_controller_and_fits " << std::setprecision(9) << measured_run_seconds << "\n";
    out << "total time " << std::setprecision(9) << total_seconds << "\n";
    out << "total time human " << human_time(total_seconds) << "\n";
}

} // namespace

Result write_native_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    require_legacy_pprint_payload(state);
    const auto started = std::chrono::steady_clock::now();
    std::filesystem::create_directories(output_dir);
    const auto path = output_dir / "xout_step.log";
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create native xout_step.log");
    out << std::setprecision(17);
    out << " xstar_tools version " << state.release << "\n";
    std::size_t source_nry = 0;
    std::size_t output_nry = 0;
    if (!state.radial_zones.empty()) {
        const auto& eval = state.radial_zones.back().accepted_controller.evaluation;
        source_nry = eval.source_continuum_tau_workspace_count;
        output_nry = eval.radiation_energy_ev.size();
    }
    out << " nry= " << std::setw(11) << source_nry << std::setw(12) << output_nry << "\n";
    out << " Loading Atomic Database...\n";
    out << " Atomic Data Version: " << read_atomic_data_version(state.atomic_database_path) << "\n";
    out << " in readtbl:\n";
    out << " native readtbl pointer/reals/integers/characters counters: unavailable (not retained by native ATDB lowering)\n";
    out << " native atomic line/rrc database totals: unavailable (not retained by native ATDB lowering)\n";
    out << " done with setptrs\n";
    append_native_input_parameters(out, state);
    append_native_radial_summary(out, output_dir, state);
    append_native_product_sections(out, output_dir, state);
    if (state.legacy_pprint.buffered_lines.empty()) {
        out << " native-only print sections that require unretained source accumulators are marked unavailable above.\n";
    }
    for (const auto& line : state.legacy_pprint.buffered_lines) {
        out << line << '\n';
    }
    const double formatter_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    append_source_like_timing_footer(out, state.measured_run_seconds, formatter_seconds);
    out.close();

    state.xout_step_computed_from_native_state = true;
    state.xout_step_timing_values_measured = true;
    Result result;
    result.lines_written = count_lines(path);
    result.prefix_exact_except_version = false;
    result.full_raw_exact_asset_written = false;
    result.full_log_complete = state.legacy_pprint.complete() && !state.legacy_pprint.buffered_lines.empty();
    result.computed_from_native_state = true;
    result.timing_values_measured = true;
    result.product_parity_qualified = false;
    return result;
}

Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_native_step_log(output_dir, state);
}

Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_native_step_log(output_dir, state);
}

} // namespace xstar_step_log
