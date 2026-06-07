#include "xstar_backend_common.hpp"
#include "compact_arrays.hpp"
#include <cstdint>
#include <sstream>
#include <algorithm>
#include <cmath>
#include <chrono>
#include <vector>
#include <limits>

namespace {

bool is_supported_mg_record(long long rate_type, long long data_type) {
    if (rate_type == 7 && (data_type == 49 || data_type == 53)) {
        return true;
    }
    // Type 50/51 are not product-active in v0.6.8, but the coarse ABI can
    // identify their topology and count them as C++-supported classification
    // work.  Matrix/rate row generation remains disabled until a later parity
    // package owns the full row application boundary.
    if (data_type == 50 || data_type == 51) {
        return true;
    }
    return false;
}

void zero_counters(std::int64_t* counters, int counters_size) {
    if (counters == nullptr || counters_size <= 0) return;
    for (int i = 0; i < counters_size; ++i) counters[i] = 0;
}

int eval_mg_ion_accumulator_impl(
    int element_z,
    int ion_index,
    int ion_stage,
    int n_levels,
    int n_parent_levels,
    int n_records,
    const std::int64_t* record_number,
    const std::int64_t* record_rate_type,
    const std::int64_t* record_data_type,
    const std::int64_t* record_source_index,
    std::int64_t* counters,
    int counters_size,
    char* message,
    std::size_t message_size
) {
    using namespace xstar_backend;
    if (!valid_count(n_records) || counters == nullptr || counters_size < MG_ACC_COUNTER_COUNT) {
        write_message(message, message_size, "invalid Mg-ion accumulator arguments");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    if (n_records > 0 && (record_rate_type == nullptr || record_data_type == nullptr)) {
        write_message(message, message_size, "record rate/data arrays are required when n_records > 0");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    zero_counters(counters, counters_size);

    std::int64_t cpp_supported = 0;
    std::int64_t python_fallback = 0;
    std::int64_t unsupported_rate = 0;
    std::int64_t unsupported_data = 0;
    std::int64_t previous_source_index = -9223372036854775807LL;
    std::int64_t source_order_records = 0;

    for (int i = 0; i < n_records; ++i) {
        const std::int64_t rt = record_rate_type[i];
        const std::int64_t dt = record_data_type[i];
        counters[MG_ACC_RECORDS_SEEN] += 1;
        if (record_source_index != nullptr) {
            const std::int64_t src = record_source_index[i];
            if (i == 0 || src >= previous_source_index) {
                source_order_records += 1;
            }
            previous_source_index = src;
        } else if (record_number != nullptr) {
            const std::int64_t src = record_number[i];
            if (i == 0 || src >= previous_source_index) {
                source_order_records += 1;
            }
            previous_source_index = src;
        }
        if (rt == 7) counters[MG_ACC_RATE_TYPE7_RECORDS] += 1;
        if (dt == 49) counters[MG_ACC_TYPE49_RECORDS] += 1;
        if (dt == 53) counters[MG_ACC_TYPE53_RECORDS] += 1;
        if (dt == 50) counters[MG_ACC_TYPE50_RECORDS] += 1;
        if (dt == 51) counters[MG_ACC_TYPE51_RECORDS] += 1;

        if (element_z == 12 && is_supported_mg_record(rt, dt)) {
            cpp_supported += 1;
            if (rt == 7 && dt == 49) counters[MG_ACC_TYPE49_SUPPORTED] += 1;
            if (rt == 7 && dt == 53) counters[MG_ACC_TYPE53_SUPPORTED] += 1;
            if (dt == 50) counters[MG_ACC_TYPE50_TOPOLOGY_SUPPORTED] += 1;
            if (dt == 51) counters[MG_ACC_TYPE51_TOPOLOGY_SUPPORTED] += 1;
        } else {
            python_fallback += 1;
            if (rt != 7 && dt != 50 && dt != 51) unsupported_rate += 1;
            else unsupported_data += 1;
        }
    }

    counters[MG_ACC_CPP_SUPPORTED] = cpp_supported;
    counters[MG_ACC_PYTHON_FALLBACK] = python_fallback;
    counters[MG_ACC_UNSUPPORTED_RATE_TYPE_RECORDS] = unsupported_rate;
    counters[MG_ACC_UNSUPPORTED_DATA_TYPE_RECORDS] = unsupported_data;
    counters[MG_ACC_SOURCE_ORDER_RECORDS] = source_order_records;
    counters[MG_ACC_PRODUCT_ACTIVE] = 0;
    // Product-active row generation remains off in v0.6.8.
    counters[MG_ACC_MATRIX_TERMS_EMITTED] = 0;
    counters[MG_ACC_RATE_TERMS_EMITTED] = 0;
    counters[MG_ACC_HEAT_TERMS_EMITTED] = 0;
    counters[MG_ACC_COOL_TERMS_EMITTED] = 0;

    std::ostringstream out;
    out << "Mg-ion accumulator v0.6.8 coarse ABI: element_z=" << element_z
        << "; ion_index=" << ion_index
        << "; ion_stage=" << ion_stage
        << "; n_levels=" << n_levels
        << "; n_parent_levels=" << n_parent_levels
        << "; records_seen=" << counters[MG_ACC_RECORDS_SEEN]
        << "; cpp_supported=" << cpp_supported
        << "; python_fallback=" << python_fallback
        << "; product_active=0";
    write_message(message, message_size, out.str());
    return XSTAR_BACKEND_OK;
}


double native_expo(double x) {
    return std::exp(std::min(60.0, std::max(-60.0, x)));
}

double native_dfact_log(int n) {
    return n <= 0 ? 0.0 : std::lgamma(static_cast<double>(n) + 1.0);
}

double native_hgf_int(int ia, int ib, int ic, double x) {
    const int limit = std::min(-ia, -ib);
    double ser = 1.0;
    double hyp = 1.0;
    if (limit < 0) return hyp;
    for (int n = 0; n <= limit; ++n) {
        const double den = (static_cast<double>(n) + 1.0) * (static_cast<double>(ic) + n);
        if (den == 0.0) return std::numeric_limits<double>::quiet_NaN();
        ser = ser * (static_cast<double>(ia) + n) * (static_cast<double>(ib) + n) * x / den;
        hyp += ser;
    }
    return hyp;
}

void native_anl1(int ni, int nf, int lf, int iq, double& alm, double& alp) {
    alm = 0.0;
    alp = 0.0;
    if (ni <= 0 || nf <= 0 || iq <= 0) return;
    for (int li = lf - 1; li <= lf + 1; li += 2) {
        if (li < 0) continue;
        int n = 0, np = 0, l = 0;
        if (lf > li) { n = nf; np = ni; l = lf; }
        else { n = ni; np = nf; l = li; }
        if (n == np) continue;
        const double x1 = native_dfact_log(n + l);
        const double x2 = native_dfact_log(np + l - 1);
        const double x3 = native_dfact_log(2 * l - 1);
        const double x4 = native_dfact_log(n - l - 1);
        const double x5 = native_dfact_log(np - l);
        const int ia1 = -n + l + 1;
        const int ia2 = ia1 - 2;
        const int ib = -np + l;
        const int ic = 2 * l;
        const double dn = static_cast<double>(n - np);
        if (dn == 0.0) continue;
        const double x = -4.0 * static_cast<double>(n) * static_cast<double>(np) / (dn * dn);
        const double y1 = native_hgf_int(ia1, ib, ic, x);
        const double y2 = native_hgf_int(ia2, ib, ic, x);
        if (!std::isfinite(y1) || !std::isfinite(y2)) continue;
        const int rev_i = std::abs(n - np);
        const double rev = static_cast<double>(rev_i);
        const double rn = static_cast<double>(n + np);
        if (rev <= 0.0 || rn <= 0.0) continue;
        double tlog = (static_cast<double>(l) + 1.0) * std::log(4.0 * static_cast<double>(n * np));
        tlog += (rn - 2.0 * static_cast<double>(l) - 2.0) * std::log(rev);
        tlog -= std::log(4.0) + rn * std::log(rn);
        const double diff = std::abs(y1 - y2 * std::pow(rev / rn, 2.0));
        if (!(diff > 0.0)) continue;
        const double ylog = std::log(diff) + tlog;
        const double elog = 2.0 * ylog + x1 + x2 - 2.0 * x3 - x4 - x5;
        double t = 0.0;
        if (elog < -745.0) t = 0.0;
        else if (elog > 700.0) t = std::exp(700.0);
        else t = std::exp(elog);
        double an = 2.6761e09 * std::pow(static_cast<double>(iq), 4.0) * static_cast<double>(std::max(li, lf)) * t / (2.0 * static_cast<double>(li) + 1.0);
        const double dum = std::pow(1.0 / static_cast<double>(nf * nf) - 1.0 / static_cast<double>(ni * ni), 3.0);
        an *= dum;
        if (li < lf) alm = an;
        if (li > lf) alp = an;
    }
}

void native_impcfn(double x, double& xsi, double& phi) {
    if (x <= 0.0) x = 1.0e-300;
    const double a[6] = {0.9947187, 0.6030883, -2.372843, 1.864266, -0.6305845, 8.1104480e-02};
    const double b[6] = {0.2551543, -0.5455462, 0.3096816, 4.2568920e-02, -2.0123060e-02, -4.9607030e-03};
    const double pi = std::acos(-1.0);
    if (x <= 2.0) {
        xsi = 0.0; phi = 0.0;
        const double y = std::log(x);
        double xp = 1.0, yp = 1.0;
        for (int n = 0; n < 6; ++n) {
            xsi += a[n] * xp;
            phi += b[n] * yp;
            xp *= x; yp *= y;
        }
        if (x == 1.0) phi = b[0];
        if (x < 0.05) {
            xsi = 1.0 + 0.01917 / 0.05 * x;
            const double yy = std::log(1.1229 / x);
            phi = yy + x * x / 4.0 * (1.0 - 2.0 * yy * yy);
        }
    } else {
        xsi = pi * x * std::exp(-2.0 * x) * (1.0 + 0.25 / x + 1.0 / (32.0 * x * x));
        phi = pi / 2.0 * std::exp(-2.0 * x) * (1.0 + 0.25 / x - 3.0 / (32.0 * x * x));
    }
}

double native_impactn(int n, int m, double temp, int ic, double amn) {
    if (n <= 0 || m <= 0 || ic <= 0 || temp <= 0.0 || amn <= 0.0) return 0.0;
    const double xm = 157888.0 * static_cast<double>(ic * ic) / temp / static_cast<double>(m * m);
    if (xm > 60.0) return 0.0;
    const double rm = 1.0, z1 = 1.0;
    const double tk = 8.617e-5 * temp;
    const int inc = 1, jm = 90 * inc;
    double ecm = 109737.0 * static_cast<double>(ic * ic) * (1.0 / static_cast<double>(n * n) - 1.0 / static_cast<double>(m * m));
    const double ecm3 = ecm * ecm * ecm;
    ecm = -ecm;
    if (ecm3 == 0.0) return 0.0;
    const double psi = 1.644e5 * amn / ecm3;
    const double po = (5.0 * static_cast<double>(n * n) + 1.0) / 4.0 / static_cast<double>(ic);
    double cr = 0.0, fi = 0.0, wo = 0.0, bpar = 10.0;
    const double ev = std::abs(ecm) / 8065.48;
    bool stop = false;
    for (int outer = 0; outer < 10000 && !stop; ++outer) {
        const double delb = bpar / 100.0 / static_cast<double>(inc);
        for (int j = 1; j <= jm; ++j) {
            bpar -= delb;
            if (bpar <= 0.0) bpar = 1.0e-300;
            double xsi = 0.0, phi = 0.0;
            native_impcfn(bpar, xsi, phi);
            const double inside = 2.0 * xsi * psi;
            if (inside < 0.0) continue;
            const double w = static_cast<double>(ic) * rm * ev / bpar * std::sqrt(inside);
            const double wi = w + ecm / 8065.48 / 2.0;
            if (wi / tk >= 100.0) { stop = true; break; }
            if (wi <= 0.0 || w == 0.0) continue;
            const double bo = po * ev / 2.0 / w * std::sqrt(std::max(wi * rm / 13.60, 0.0));
            double xsw = 0.0, phw = 0.0;
            native_impcfn(bo, xsw, phw);
            (void)xsw; (void)phw;
            double ff = (xsi / 2.0 + phi);
            ff *= std::exp(-wi / tk);
            const double crinc = (fi + ff) / 2.0 * (wi - wo);
            cr += crinc;
            if (cr < 1.0e-20) continue;
            fi = ff; wo = wi;
            if ((crinc / cr < 1.0e-5) && (crinc > 1.0e-7)) { stop = true; break; }
        }
    }
    if (tk == 0.0) return 0.0;
    cr = 6.900e-5 * z1 * z1 * std::sqrt(rm / temp) * psi * cr / tk;
    const double cmm = cr * static_cast<double>(m * m) * std::exp(std::min(xm, 700.0));
    return std::max(0.0, cmm);
}

double native_expint_scaled(double x) {
    if (x > 1.0) {
        const double b1=9.5733223454,b2=25.6329561486,b3=21.0996530827,b4=3.9584969228;
        const double c1=8.5733287401,c2=18.0590169730,c3=8.6347608925,c4=0.2677737343;
        const double x2=x*x,x3=x2*x,x4=x2*x2;
        return (x4+c1*x3+c2*x2+c3*x+c4)/(x4+b1*x3+b2*x2+b3*x+b4);
    }
    const double a0=-0.57721566,a1=0.99999193,a2=-0.24991055,a3=0.05519968,a4=-0.00976004,a5=0.00107857;
    if (x == 0.0) return std::numeric_limits<double>::infinity();
    double e1 = 0.0;
    if (x > 0.0) e1 = a0+a1*x+a2*x*x+a3*x*x*x+a4*std::pow(x,4.0)+a5*std::pow(x,5.0)-std::log(x);
    else e1 = -a0+a1*x+a2*x*x+a3*x*x*x+a4*std::pow(x,4.0)+a5*std::pow(x,5.0)-std::log(-x);
    return e1*x*native_expo(x);
}

void native_eint(double t, double& e1, double& e2, double& e3) {
    if (t == 0.0) { e1=e2=e3=0.0; return; }
    const double ss = native_expint_scaled(t);
    e1 = ss / std::max(1.0e-34, t * native_expo(t));
    e2 = std::exp(-t) - t * e1;
    e3 = 0.5 * (native_expo(-t) - t * e2);
}

double native_szcoll(int ni, int nj, double tt, int ic) {
    if (ni <= 0 || nj <= ni || ic <= 0 || tt <= 0.0) return 0.0;
    const double abethe[11]={1.30,0.59,0.38,0.286,0.229,0.192,0.164,0.141,0.121,0.105,0.100};
    const double hbethe[11]={1.48,3.64,5.93,8.32,10.75,12.90,15.05,17.20,19.35,21.50,2.15};
    const double rbethe[11]={1.83,1.60,1.53,1.495,1.475,1.46,1.45,1.45,1.46,1.47,1.48};
    const double fvg1[5]={1.133,1.0785,0.9935,0.2328,-0.1296};
    const double fvg2[5]={-0.4059,-0.2319,0.6282,-0.5598,0.5299};
    const double fvg3[5]={0.07014,0.02947,0.3887,-1.181,1.47};
    const double eion=1.578203e5, cons=8.63e-6;
    const double rn2=std::pow(static_cast<double>(ni)/static_cast<double>(nj),2.0);
    double g1=0,g2=0,g3=0;
    if (ni==1) {g1=fvg1[0];g2=fvg2[0];g3=fvg3[0];}
    else if (ni==2) {g1=fvg1[1];g2=fvg2[1];g3=fvg3[1];}
    else {g1=fvg1[2]+fvg1[3]/ni+fvg1[4]/static_cast<double>(ni*ni);g2=(fvg2[2]+fvg2[3]/ni+fvg2[4]/static_cast<double>(ni*ni))/ni*(-1.0);g3=(fvg3[2]+fvg3[3]/ni+fvg3[4]/static_cast<double>(ni*ni))/static_cast<double>(ni*ni);}
    const double xx=1.0-rn2;
    if (xx==0.0) return 0.0;
    const double gaunt=g1+g2/xx+g3/(xx*xx);
    const double fnn=1.9603*gaunt/std::pow(xx,3.0)*ni/std::pow(static_cast<double>(nj),3.0);
    double an=0,hn=0,rrn=0;
    if (ni<11) {an=abethe[ni-1];hn=hbethe[ni-1];rrn=rbethe[ni-1];}
    else {an=abethe[10]/ni;hn=hbethe[10]*ni;rrn=rbethe[10];}
    const double ann=fnn*4.0*std::pow(static_cast<double>(ni),4.0)/xx;
    const double dnn=ann*hn*(std::pow(xx,rrn)-an*rn2);
    double cnn=1.12*ni*ann*xx;
    if ((nj-ni)==1) cnn*=std::exp(-0.006*std::pow(static_cast<double>(ni-1),6.0)/ic);
    const double yy=eion*ic*ic*(1.0/static_cast<double>(ni*ni)-1.0/static_cast<double>(nj*nj))/tt;
    double e1=0,e2=0,e3=0; native_eint(yy,e1,e2,e3); (void)e2;(void)e3;
    const double rate=cons/std::sqrt(tt)/ni/ni/ic/ic*(dnn*std::exp(-yy)+(ann+yy*(cnn-dnn))*e1);
    return std::max(0.0, rate);
}

void native_erc(int n, int m, double temp, int ic, double asum, double& se, double& sd) {
    se=0.0; sd=0.0;
    if (n<=0 || m<=n || ic<=0 || temp<=0.0) return;
    const double rn=n, rm=m, ric=ic;
    if (ic!=1) {
        if (ic<10) {
            const double ym0=157803.0*ic*ic/temp/(m*m);
            if (ym0>40.0) return;
            const double sm=native_impactn(n,m,temp,ic,asum);
            const double ym=157803.0*ric*ric/temp/(rm*rm);
            const double xn=1.0/(rn*rn)-1.0/(rm*rm);
            const double yn=157803.0*ric*ric*xn/temp;
            const double sval=sm/(rn*rn)/std::exp(std::min(ym,700.0));
            sd=sval*rn*rn/(rm*rm);
            se=yn<40.0?sval*std::exp(-yn):0.0;
            se=std::max(0.0,se);sd=std::max(0.0,sd);return;
        }
        se=native_szcoll(n,m,temp,ic);
        const double yn=157803.0*ric*ric*(1.0/(rn*rn)-1.0/(rm*rm))/temp;
        sd=se*std::exp(std::min(50.0,yn))*rn*rn/(rm*rm);
        se=std::max(0.0,se);sd=std::max(0.0,sd);return;
    }
    const double xn=1.0/(rn*rn)-1.0/(rm*rm);
    if (xn==0.0) return;
    const double f=-1.2456e-10*asum/(xn*xn);
    const double yn=157803.0*xn/temp;
    const double z=(n==1)?yn+0.45*xn:1.94*xn*std::pow(rn,0.43)+yn;
    const double dif=z-yn;
    const double e1y=native_expint_scaled(yn), e1z=native_expint_scaled(z);
    const double e2=(1.0-e1y)/yn-native_expo(-dif)*(1.0-e1z)/z;
    const double ann=-2.0*f*rm*rm/xn/rn/rn;
    double bn=(4.0-18.63/rn+36.24/(rn*rn)-28.09/(rn*rn*rn))/rn;
    if (n==1) bn=-0.603;
    const double bnn=(1.0+4.0/(xn*rn*rn*3.0)+bn/(std::pow(rn,4.0)*xn*xn))*4.0/(std::pow(rm,3.0)*xn*xn);
    double sval=ann*((1.0/yn+0.5)*e1y/yn-(1.0/z+0.5)*e1z*native_expo(-dif)/z);
    sval+=e2*(bnn-ann*std::log(2.0/xn));
    sval=1.095e-10*yn*yn*std::sqrt(temp)*sval/xn;
    sd=sval*rn/rm*rn/rm; se=sval*native_expo(-yn);
    se=std::max(0.0,se);sd=std::max(0.0,sd);
}

double native_e1_from_scaled(double x) {
    if (x<=0.0) return std::numeric_limits<double>::infinity();
    return native_expint_scaled(x)/std::max(1.0e-300,x*native_expo(x));
}

double native_velimp(int n,int l,double temp,int ic,double ne,double asum) {
    const double z1=1.0,rm=1800.0;
    if (n<=0||l<=0||l>=n||ic<=0||temp<=0.0||ne<=0.0||asum<=0.0) return 0.0;
    const double den=l*(n*n-l*l)+(l+1)*(n*n-(l+1)*(l+1));
    const double dnl=6.0*z1/ic*z1/ic*n*n*(n*n-l*l-l-1);
    if (den<=0.0||dnl<=0.0) return 0.0;
    const double pi=2.0*std::acos(0.0),pa=0.72/asum,pd=6.90*std::sqrt(temp/ne),alfa=3.297e-12*rm/temp;
    const double b=1.157*std::sqrt(dnl),bb=b*b,va=pd/pa,vd=b/pd;
    if (va<=0.0||vd<=0.0||alfa<=0.0) return 0.0;
    const double vb=std::sqrt(va*vd),ava=alfa*va*va,avb=alfa*vb*vb,avd=alfa*vd*vd;
    const double xa=native_expo(-ava),xb=native_expo(-avb),xd=native_expo(-avd);
    const double ea=ava<50.0?native_e1_from_scaled(ava):0.0,eb=native_e1_from_scaled(avb),ed=avd<50.0?native_e1_from_scaled(avd):0.0;
    double cn=0.0;
    if (va>vd) {
        if (avb>1.0e-3) cn=std::sqrt(pi*alfa)*(pa*pa*(2.0/(alfa*alfa)-xb*(std::pow(vb,4.0)+2.0*vb*vb/alfa+2.0/(alfa*alfa)))+bb*xb+2.0*bb*eb-bb*ea);
        else cn=std::sqrt(pi*alfa)*bb*(1.0+avb*(1.0/3.0-avb/4.0)+2.0*eb-ea);
    } else {
        double ca=0.0;
        if (ava>1.0e-3) ca=std::sqrt(pi*alfa)*pa*pa*(2.0/(alfa*alfa)-xa*(std::pow(va,4.0)+2.0*va*va/alfa+2.0/(alfa*alfa)));
        else ca=std::sqrt(pi*alfa)*pd*pd*std::pow(va,4.0)*alfa*(1.0/3.0-ava/4.0+ava*ava/10.0);
        const double cad=std::sqrt(pi*alfa)*pd*pd/alfa*(xa*(1.0+ava)-xd*(1.0+avd));
        const double cd=std::sqrt(pi*alfa)*bb*(xd+ed);
        cn=ca+cad+cd;
    }
    cn=cn*l*(n*n-l*l)/den;
    return std::isfinite(cn)?std::max(0.0,cn):0.0;
}

bool native_type63_scalars(int ni,int li,int nf,int lf,int iq,double temp,double ne,double ei,double ef,double gi,double gf,double out[6]) {
    for (int q=0;q<6;++q) out[q]=0.0;
    if (ni<=0||nf<=0||li<0||lf<0||iq<=0||temp<=0.0||ne<0.0) return false;
    double qf=0.0,qr=0.0;
    if (ni==nf) {
        if (std::abs(lf-li)!=1) return true;
        const int lff=std::min(lf,li),lii=std::max(lf,li),li1=std::max(1,lff);
        double sum=0.0;
        for (int nn=li1;nn<ni;++nn) {
            if (lii>=1) {double alm=0,alp=0;native_anl1(ni,nn,lii-1,iq,alm,alp);sum+=alp;}
            if (nn>lii+1) {double alm=0,alp=0;native_anl1(ni,nn,lii+1,iq,alm,alp);sum+=alm;}
        }
        if (!(sum>0.0)) return true;
        const double cn=native_velimp(ni,lii,temp,iq,ne,sum);
        if (!(cn>0.0)) return true;
        if (!(gi>0.0)) gi=2.0*li+1.0;
        if (!(gf>0.0)) gf=2.0*lf+1.0;
        if (lf<li) {qf=cn;qr=gf!=0.0?cn*gi/gf:0.0;}
        else {qr=cn;qf=gi!=0.0?cn*gf/gi:0.0;}
    } else {
        if (std::abs(lf-li)!=1) return true;
        const int nu=std::max(ni,nf),nll=std::min(ni,nf);
        double sum=0.0,aa1=0.0;
        for (int lff=0;lff<nll;++lff) {
            double alm=0,alp=0;native_anl1(nu,nll,lff,iq,alm,alp);
            sum+=alp*(2.0*lff+3.0);
            if (lff>0) sum+=alm*(2.0*lff-1.0);
            if (lff==lf&&li>lf) aa1=alp;
            if (lff==lf&&li<lf) aa1=alm;
        }
        if (!(sum>0.0)||!(aa1>0.0)) return true;
        double se=0.0,sd=0.0;native_erc(nll,nu,temp,iq,sum,se,sd);
        qf=se*(2.0*lf+1.0)*aa1/sum;
        qr=sd*(2.0*li+1.0)*aa1/sum;
        if (nf>ni||lf>li) std::swap(qf,qr);
    }
    out[0]=qf*ne;out[1]=qr*ne;
    const double de=std::abs(ef-ei),erg=1.602197e-12;
    out[4]=out[1]*de*erg;out[5]=out[0]*de*erg;
    return std::isfinite(out[0])&&std::isfinite(out[1])&&std::isfinite(out[4])&&std::isfinite(out[5]);
}

int native_lower_bracket(double energy,const double* grid,int n) {
    if (n<=1||energy<=grid[0]) return 0;
    int lo=0,hi=n-1;
    while (lo+1<hi) {int mid=(lo+hi)/2;if (grid[mid]<=energy) lo=mid;else hi=mid;}
    return grid[hi]<=energy?hi:lo;
}

double native_type88_photo_rate(const double* raw,int raw_count,double threshold,const double* epi,const double* bremsa,int n_grid,int phextrap_limit) {
    const int n0=raw_count/2;
    if (n0<=0||threshold<=0.0||n_grid<3||phextrap_limit<3) return 0.0;
    std::vector<double> e,s;e.reserve(n_grid);s.reserve(n_grid);
    for (int j=0;j<n0;++j) {e.push_back(raw[2*j]);s.push_back(std::max(0.0,raw[2*j+1]*1.0e-18));}
    int base=std::max(static_cast<int>(e.size())-2,0);
    double e1=e[base]*13.6+threshold,s1=s[base];
    while (s1>1.0e-27&&static_cast<int>(e.size())<phextrap_limit&&e1<2.0e5) {
        const double e2=e1*1.3,s2=s1/(1.3*1.3*1.3);
        e.push_back((e2-threshold)/13.6);s.push_back(s2);e1=e2;s1=s2;
    }
    const int ntmp=std::min(e.size(),s.size());
    if (ntmp<=0) return 0.0;
    const int numcon2=std::max(2,n_grid/50),nphint1=n_grid-numcon2;
    std::vector<double> sgbar(n_grid,0.0),xs(ntmp),ys(ntmp);
    for (int j=0;j<ntmp;++j) {xs[j]=threshold+e[j]*13.605692;ys[j]=std::max(0.0,s[j]);}
    int nb1=native_lower_bracket(xs[0],epi,nphint1);
    if (nb1+1>=nphint1) return 0.0;
    sgbar[std::max(0,nb1-1)]=0.0;sgbar[nb1]=0.0;
    int k=nb1,j=0;double egrid=epi[k],e2=xs[j],ss2=ys[j];
    if (egrid<e2&&k+1<n_grid) {++k;egrid=epi[k];}
    double e1o=e2,integral=0.0,e2o=e2,s2o=ss2,s2t=ss2,e2t=egrid;
    bool done=false;int iterations=0,max_iter=std::max(8,4*(n_grid+ntmp));
    while (!done&&iterations<max_iter&&k<n_grid) {
        ++iterations;bool advanced=false;
        while (e2<egrid&&j<ntmp-2) {++j;e2o=e2;s2o=ss2;e2=xs[j];ss2=ys[j];integral+=(ss2+s2o)*(e2-e2o)/2.0;advanced=true;}
        if (!advanced&&iterations==1) {e2o=e2;s2o=ss2;}
        integral-=(ss2+s2o)*(e2-e2o)/2.0;e2t=egrid;
        s2t=(e2-e2o>1.0e-8)?s2o+(ss2-s2o)*(e2t-e2o)/(e2-e2o+1.0e-24):s2o;
        integral+=(s2t+s2o)*(e2t-e2o)/2.0;
        double den=egrid-e1o;sgbar[k]=std::abs(den)>1.0e-36?integral/den:0.0;e1o=egrid;++k;if(k>=n_grid)break;egrid=epi[k];
        while (egrid<e2&&k<n_grid-1) {e2t=egrid;s2t=(e2-e2o>1.0e-8)?s2o+(ss2-s2o)*(e2t-e2o)/(e2-e2o):s2o;integral=s2t*(egrid-e1o);den=egrid-e1o;sgbar[k]=std::abs(den)>1.0e-36?integral/den:0.0;e1o=egrid;++k;if(k>=n_grid)break;egrid=epi[k];}
        integral=(ss2+s2t)*(e2-e2t)/2.0;
        if (k>=nphint1-1||j>=ntmp-2) done=true;
    }
    const int klmax=std::max(nb1,k-1);
    if (iterations>=max_iter||nb1>=klmax||nb1>=n_grid) return 0.0;
    double sgtpp=sgbar[nb1],bremtmpp=bremsa[nb1]/12.56,epiip=epi[nb1];
    double temprp=epiip!=0.0?12.56*sgtpp*bremtmpp/epiip:0.0,sumr=0.0;
    int kl=nb1;
    while (kl<klmax&&kl+1<n_grid) {
        sgtpp=sgbar[kl+1];bremtmpp=bremsa[kl+1]/12.56;const double epii=epi[kl];epiip=epi[kl+1];
        const double tempr=temprp;temprp=epiip!=0.0?12.56*sgtpp*bremtmpp/epiip:0.0;const double w=(epiip-epii)/2.0;sumr+=tempr*w+temprp*w;++kl;
    }
    return std::isfinite(sumr)?sumr:0.0;
}

} // namespace

extern "C" {

int xstar_engine_abi_version() {
    return 5;
}

const char* xstar_engine_backend_name() {
    return "xstar_engine_mg_rate_payload_native_scalar_type88_full_grid_hotfix_v032";
}

int xstar_engine_feature_flags() {
    // bit 0: Mg-ion accumulator ABI present.
    // bit 1: coarse record traversal/classification implemented.
    // bit 2: compact packet counters implemented.
    // bit 3: evaluation-level Mg rate-payload orchestration shadow.
    return 1 | 2 | 4 | 8 | 16 | 32;
}

int xstar_engine_probe(int element_z, int ion_index, int n_records, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_records)) {
        xstar_backend::write_message(message, message_size, "invalid negative n_records");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_engine.so v0.6.32 Mg-ion accumulator, row orchestration, and native scalar shadow ABI available; element_z=" << element_z
        << "; ion_index=" << ion_index << "; n_records=" << n_records
        << "; product-active matrix/rate emission disabled";
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

int xstar_matrix_eval_mg_ion_accumulator_v1(
    int element_z,
    int ion_index,
    int ion_stage,
    int n_levels,
    int n_parent_levels,
    int n_records,
    const std::int64_t* record_number,
    const std::int64_t* record_rate_type,
    const std::int64_t* record_data_type,
    const std::int64_t* record_source_index,
    std::int64_t* counters,
    int counters_size,
    char* message,
    std::size_t message_size
) {
    return eval_mg_ion_accumulator_impl(
        element_z, ion_index, ion_stage, n_levels, n_parent_levels, n_records,
        record_number, record_rate_type, record_data_type, record_source_index,
        counters, counters_size, message, message_size);
}

// Backward-compatible v0.6.1 symbol.  It maps the shorter skeleton call onto
// the v0.6.8 coarse ABI without product-active row generation.
int xstar_engine_eval_mg_ion_accumulator_v1(
    int element_z,
    int ion_index,
    int n_records,
    const std::int64_t* record_rate_type,
    const std::int64_t* record_data_type,
    std::int64_t* counters,
    int counters_size,
    char* message,
    std::size_t message_size
) {
    return eval_mg_ion_accumulator_impl(
        element_z, ion_index, 0, 0, 0, n_records,
        nullptr, record_rate_type, record_data_type, nullptr,
        counters, counters_size, message, message_size);
}

}

extern "C" int xstar_engine_eval_mg_rate_payload_shadow_v1(
    int n_records,
    const std::int64_t* meta_i64,
    int meta_stride,
    const double* rates_f64,
    int rates_stride,
    int max_terms,
    std::int64_t* out_i64,
    int out_i64_stride,
    double* out_f64,
    int out_f64_stride,
    double* timing_f64,
    int timing_size,
    std::int64_t* stats,
    int stats_size,
    char* message,
    std::size_t message_size
) {
    using namespace xstar_backend;
    if (!valid_count(n_records) || meta_stride < 12 || rates_stride < 7 ||
        out_i64_stride < 16 || out_f64_stride < 4 || max_terms < 0 ||
        timing_f64 == nullptr || timing_size < 3 || stats == nullptr || stats_size < 16) {
        write_message(message, message_size, "invalid rate-payload shadow arguments");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    if (n_records > 0 && (meta_i64 == nullptr || rates_f64 == nullptr || out_i64 == nullptr || out_f64 == nullptr)) {
        write_message(message, message_size, "null rate-payload shadow array");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    for (int i = 0; i < stats_size; ++i) stats[i] = 0;
    for (int i = 0; i < timing_size; ++i) timing_f64[i] = 0.0;
    using clock_t = std::chrono::steady_clock;
    const auto total_t0 = clock_t::now();
    int emitted = 0;
    for (int k = 0; k < n_records; ++k) {
        const auto eval_t0 = clock_t::now();
        const std::int64_t* m = meta_i64 + static_cast<std::int64_t>(k) * meta_stride;
        const double* r = rates_f64 + static_cast<std::int64_t>(k) * rates_stride;
        const long long record = m[0], rate_type = m[1], data_type = m[2];
        const long long ion_index = m[3], ion_stage = m[4], compact_start = m[5];
        const long long basis_n_rows = m[6], idest1 = m[7], idest2 = m[8];
        const long long lower_endpoint = m[9], upper_endpoint = m[10], term_start = m[11];
        stats[0] += 1;
        bool family = (rate_type == 4 && data_type == 50) ||
                      (rate_type == 3 && data_type == 51) ||
                      (rate_type == 3 && data_type == 63) ||
                      (rate_type == 42 && data_type == 88);
        if (!family) { stats[4] += 1; timing_f64[0] += std::chrono::duration<double>(clock_t::now() - eval_t0).count(); continue; }
        if (rate_type == 4 && data_type == 50) stats[8] += 1;
        if (rate_type == 3 && data_type == 51) stats[9] += 1;
        if (rate_type == 3 && data_type == 63) stats[10] += 1;
        if (rate_type == 42 && data_type == 88) stats[11] += 1;
        bool finite = true;
        for (int j = 0; j < 7; ++j) finite = finite && std::isfinite(r[j]);
        if (!finite || record <= 0 || basis_n_rows <= 0 || compact_start <= 0 ||
            idest1 <= 0 || idest2 <= 0 || lower_endpoint <= 0 || upper_endpoint <= 0) {
            stats[5] += 1;
            timing_f64[0] += std::chrono::duration<double>(clock_t::now() - eval_t0).count();
            continue;
        }
        timing_f64[0] += std::chrono::duration<double>(clock_t::now() - eval_t0).count();
        if (emitted + 4 > max_terms) { stats[6] += 1; break; }
        const auto terms_t0 = clock_t::now();
        const double ans1 = r[0], ans2 = r[1], ans3 = r[2], ans4 = r[3], ans5 = r[4], ans6 = r[5];
        const double xpx = r[6];
        long long raw_lower = compact_start + lower_endpoint - 1;
        long long raw_upper = compact_start + upper_endpoint - 1;
        long long row_lower = std::min(basis_n_rows, raw_lower);
        long long row_upper = std::min(basis_n_rows, raw_upper);
        const long long rows[4] = {row_upper, row_lower, row_lower, row_upper};
        const long long cols[4] = {row_lower, row_upper, row_lower, row_upper};
        const long long raw_rows[4] = {raw_upper, raw_lower, raw_lower, raw_upper};
        const long long raw_cols[4] = {raw_lower, raw_upper, raw_lower, raw_upper};
        const long long roles[4] = {1, 2, 3, 4};
        const double vals[4][4] = {
            {ans1, ans2, 0.0, 0.0},
            {ans2, ans1, 0.0, 0.0},
            {-ans1, -ans1, ans4 * xpx, ans6 * xpx},
            {-ans2, -ans2, -ans3 * xpx, -ans5 * xpx},
        };
        for (int q = 0; q < 4; ++q) {
            std::int64_t* oi = out_i64 + static_cast<std::int64_t>(emitted) * out_i64_stride;
            double* of = out_f64 + static_cast<std::int64_t>(emitted) * out_f64_stride;
            oi[0] = term_start + q; oi[1] = record; oi[2] = data_type; oi[3] = rate_type;
            oi[4] = ion_index; oi[5] = ion_stage; oi[6] = roles[q]; oi[7] = rows[q]; oi[8] = cols[q];
            oi[9] = idest1; oi[10] = idest2; oi[11] = lower_endpoint; oi[12] = upper_endpoint;
            oi[13] = raw_rows[q]; oi[14] = raw_cols[q]; oi[15] = (raw_rows[q] != rows[q] || raw_cols[q] != cols[q]) ? 1 : 0;
            of[0] = vals[q][0]; of[1] = vals[q][1]; of[2] = vals[q][2]; of[3] = vals[q][3];
            ++emitted;
        }
        stats[1] += 1;
        timing_f64[1] += std::chrono::duration<double>(clock_t::now() - terms_t0).count();
    }
    timing_f64[2] = std::chrono::duration<double>(clock_t::now() - total_t0).count();
    stats[2] = emitted;
    stats[3] = emitted / 4;
    stats[7] = (stats[5] == 0 && stats[6] == 0) ? 1 : 0;
    std::ostringstream out;
    out << "rate-payload batched orchestration shadow: records=" << n_records
        << "; supported=" << stats[1] << "; terms=" << emitted
        << "; invalid=" << stats[5] << "; overflow=" << stats[6];
    write_message(message, message_size, out.str());
    return XSTAR_BACKEND_OK;
}


extern "C" int xstar_engine_eval_mg_rate_payload_native_scalars_v1(
    int n_records,
    const std::int64_t* meta_i64,
    int meta_stride,
    const double* context_f64,
    int context_stride,
    const double* payload_f64,
    int payload_size,
    const double* epi_f64,
    const double* bremsa_f64,
    int n_grid,
    double* out_ans_f64,
    int out_stride,
    double* timing_f64,
    int timing_size,
    std::int64_t* stats,
    int stats_size,
    char* message,
    std::size_t message_size
) {
    using namespace xstar_backend;
    if (!valid_count(n_records) || meta_stride < 14 || context_stride < 14 || payload_size < 0 ||
        n_grid < 3 || out_stride < 6 || timing_f64 == nullptr || timing_size < 3 ||
        stats == nullptr || stats_size < 16) {
        write_message(message, message_size, "invalid native scalar shadow arguments");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    if (n_records > 0 && (!meta_i64 || !context_f64 || !out_ans_f64 || !epi_f64 || !bremsa_f64)) {
        write_message(message, message_size, "null native scalar shadow array");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    for (int i=0;i<stats_size;++i) stats[i]=0;
    for (int i=0;i<timing_size;++i) timing_f64[i]=0.0;
    using clock_t=std::chrono::steady_clock;
    const auto total_t0=clock_t::now();
    for (int k=0;k<n_records;++k) {
        const auto eval_t0=clock_t::now();
        const std::int64_t* m=meta_i64+static_cast<std::int64_t>(k)*meta_stride;
        const double* c=context_f64+static_cast<std::int64_t>(k)*context_stride;
        double* out=out_ans_f64+static_cast<std::int64_t>(k)*out_stride;
        for (int q=0;q<out_stride;++q) out[q]=0.0;
        const long long record=m[0],rt=m[1],dt=m[2];
        const int ni=static_cast<int>(m[7]),li=static_cast<int>(m[8]),nf=static_cast<int>(m[9]),lf=static_cast<int>(m[10]),iq=static_cast<int>(m[11]);
        const int off=static_cast<int>(m[12]),count=static_cast<int>(m[13]);
        stats[0]+=1;
        bool ok=false;
        if (rt==3&&dt==63) {
            ok=native_type63_scalars(ni,li,nf,lf,iq,c[6],c[7],c[8],c[9],c[10],c[11],out);
            stats[8]+=1;
        } else if (rt==42&&dt==88) {
            if (off>=0&&count>=4&&off+count<=payload_size&&payload_f64) {
                out[0]=native_type88_photo_rate(payload_f64+off,count,c[12],epi_f64,bremsa_f64,n_grid,static_cast<int>(c[13]));
                ok=std::isfinite(out[0]);
            }
            stats[9]+=1;
        } else {
            stats[4]+=1;
        }
        if (ok) stats[1]+=1; else stats[5]+=1;
        timing_f64[0]+=std::chrono::duration<double>(clock_t::now()-eval_t0).count();
    }
    timing_f64[2]=std::chrono::duration<double>(clock_t::now()-total_t0).count();
    stats[2]=n_records*6;
    stats[7]=(stats[5]==0&&stats[4]==0)?1:0;
    std::ostringstream out;
    out << "native scalar shadow: records=" << n_records << "; evaluated=" << stats[1]
        << "; type63=" << stats[8] << "; type88=" << stats[9] << "; invalid=" << stats[5];
    write_message(message,message_size,out.str());
    return XSTAR_BACKEND_OK;
}
