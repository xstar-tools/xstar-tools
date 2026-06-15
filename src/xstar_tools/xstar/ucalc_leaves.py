"""Leaf-routine translations used by the source-faithful ``ucalc`` port.

The functions in this module mirror small XSTAR Fortran source files rather
than exposing a new high-level physics API.  Inputs retain the units and array
layouts used by the original routines so the dispatcher can be compared
record-by-record with ``ucalc.f90``.
"""
from __future__ import annotations

from .constants import LEGACY_BOLTZMANN_KEV_PER_K

import math
from typing import Iterable, Sequence

import numpy as np

RYDBERG_EV = 13.605692
ERG_PER_EV = 1.602197e-12
KBOLTZ_KEV_K = LEGACY_BOLTZMANN_KEV_PER_K
UPSILON_COLL_COEFF = 8.629e-6


def expo(x: float) -> float:
    return math.exp(min(max(float(x), -60.0), 60.0))


def exintn(x: float, n: int, e1_in: float = -1.0) -> float:
    """Translation of ``exintn.f90`` for n=1..6."""
    x = float(x)
    if x <= 0.0:
        return 0.0
    e1 = float(e1_in)
    if n == 1 or e1 < 0.0:
        if x <= 1.0:
            a = (7.122452e-07,1.766345e-06,2.928433e-05,.0002335379,.001664156,.01041576,.05555682,.2500001,.9999999,.57721566490153)
            e1 = ((((((((a[0]*x-a[1])*x+a[2])*x-a[3])*x+a[4])*x-a[5])*x+a[6])*x-a[7])*x+a[8])*x-math.log(x)-a[9]
        else:
            b=(8.5733287401,18.059016973,8.6347608925,.2677737343,9.5733223454,25.6329561486,21.0996530827,3.9584969228)
            x2=x*x; x3=x2*x; x4=x2*x2
            e1=(x4+b[0]*x3+b[1]*x2+b[2]*x+b[3])/(x4+b[4]*x3+b[5]*x2+b[6]*x+b[7])/(x*expo(x))
    if n == 1: return e1
    if n == 2: return expo(-x)-x*e1
    if n == 3: return (x*x*e1+expo(-x)*(1.0-x))/2.0
    if n == 4: return (expo(-x)*(2.0-x+x*x)-x**3*e1)/6.0
    if n == 5: return (expo(-x)*(6.0-2*x+x*x-x**3)+x**4*e1)/24.0
    if n == 6: return (expo(-x)*(24.0-6*x+2*x*x-x**3+x**4)-x**5*e1)/120.0
    raise ValueError("exintn supports n=1..6")


def natural_cubic_spline(x: Sequence[float], y: Sequence[float], value: float) -> float:
    """Natural cubic spline compatible with XSTAR's prepspline/calcspline use."""
    xa=np.asarray(x,dtype=float); ya=np.asarray(y,dtype=float)
    n=min(xa.size,ya.size)
    if n == 0: return 0.0
    if n == 1: return float(ya[0])
    xa=xa[:n]; ya=ya[:n]
    if value <= xa[0]: return float(ya[0])
    if value >= xa[-1]: return float(ya[-1])
    h=np.diff(xa)
    if np.any(h <= 0): return float(np.interp(value,xa,ya))
    alpha=np.zeros(n)
    alpha[1:-1]=3.0/h[1:]*(ya[2:]-ya[1:-1])-3.0/h[:-1]*(ya[1:-1]-ya[:-2])
    l=np.ones(n); mu=np.zeros(n); z=np.zeros(n)
    for i in range(1,n-1):
        l[i]=2*(xa[i+1]-xa[i-1])-h[i-1]*mu[i-1]
        if abs(l[i]) < 1e-300: return float(np.interp(value,xa,ya))
        mu[i]=h[i]/l[i]; z[i]=(alpha[i]-h[i-1]*z[i-1])/l[i]
    b=np.zeros(n-1); c=np.zeros(n); d=np.zeros(n-1)
    for j in range(n-2,-1,-1):
        c[j]=z[j]-mu[j]*c[j+1]
        b[j]=(ya[j+1]-ya[j])/h[j]-h[j]*(c[j+1]+2*c[j])/3
        d[j]=(c[j+1]-c[j])/(3*h[j])
    j=max(0,min(int(np.searchsorted(xa,value)-1),n-2)); dx=value-xa[j]
    return float(ya[j]+b[j]*dx+c[j]*dx*dx+d[j]*dx**3)


def phextrap(energy_ryd: Sequence[float], sigma_cm2: Sequence[float], threshold_ev: float, max_points: int) -> tuple[np.ndarray,np.ndarray]:
    """Translation of ``phextrap.f90``."""
    e=list(float(v) for v in energy_ryd); s=list(max(float(v),0.0) for v in sigma_cm2)
    n=min(len(e),len(s))
    if n <= 0: return np.asarray([],float),np.asarray([],float)
    e=e[:n]; s=s[:n]
    # The source uses ntmp-1 as the last physical point.
    base=max(n-2,0); e1=e[base]*13.6+threshold_ev; s1=s[base]
    while s1 > 1e-27 and len(e) < max_points and e1 < 2e5:
        e2=e1*1.3; s2=s1/(1.3**3)
        # The source overwrites/extends from ntmp-1.
        e.append((e2-threshold_ev)/13.6); s.append(s2)
        e1,s1=e2,s2
    return np.asarray(e,float),np.asarray(s,float)


def bkhsgo(epi_ev: Sequence[float], threshold_ev: float, d: float, b: Sequence[float], coeff: Sequence[Sequence[float]]) -> np.ndarray:
    """Translation of ``bkhsgo.f90``."""
    epi=np.asarray(epi_ev,float); out=np.zeros_like(epi)
    if not b or not coeff: return out
    j=0
    for k,energy in enumerate(epi):
        if energy < threshold_ev: continue
        xx=energy*1e-3-float(d)
        if xx <= 0: continue
        while j < len(b)-1 and xx >= float(b[j]): j += 1
        yy=math.log10(max(xx,1e-300)); row=list(coeff[min(j,len(coeff)-1)])
        tmp=0.0
        for val in reversed(row[:11]): tmp=float(val)+yy*tmp
        tmp=min(max(tmp,-50.0),24.0)
        out[k]=10.0**(tmp-24.0)
    return out


def intin(x1: float,x2: float,x0: float,temp_k: float) -> tuple[float,float]:
    ryk=7.2438e15; s1=x1*ryk/temp_k; s2=x2*ryk/temp_k; s0=x0*ryk/temp_k; dele=ryk/temp_k
    if s1-s0 < 90.0:
        ri2=math.exp(s0-s1)*((s1*s1+2*s1+2)-math.exp(s1-s2)*(s2*s2+2*s2+2))/dele/math.sqrt(dele)
        if s0 < 1e-3 and s2 < 1e-3 and s1 < 1e-3: ri2=0.0
    else: ri2=0.0
    rr=math.exp(min(700.0,s0-s1))*((s1**3)-math.exp(max(-700.0,s1-s2))*(s2**3))
    ri3=(rr/dele/math.sqrt(dele)+3*ri2)/dele
    return ri2,ri3


def milne(temp_k: float, energy_ryd: Sequence[float], sigma_mb: Sequence[float], threshold_ryd: float) -> float:
    """Translation of ``milne.f90`` returning alpha in cm3/s."""
    x=np.asarray(energy_ryd,float); y=np.asarray(sigma_mb,float); n=min(x.size,y.size)
    if n < 2 or temp_k <= 0: return 0.0
    x=x[:n]; y=y[:n]; ry=2.17896e-11; st=(x[0]+threshold_ryd)*ry
    total=0.0; previous=1.0; i=0
    while i < n-1 and abs(total-previous) > 0.01*max(abs(total),1e-300):
        i+=1; s1=(x[i-1]+threshold_ryd)*ry; s2=(x[i]+threshold_ryd)*ry
        if s2 < s1: return 0.0
        v1,v2=y[i-1],y[i]
        if v1 != 0 or v2 != 0:
            rb=(v2-v1)/(s2-s1+1e-24); ra=v2-rb*s2; ri2,ri3=intin(s1,s2,st,temp_k)
            previous=total; total += ra*ri2+rb*ri3
    return total*.79788*40.4153


def gull1(n: int, rs: float) -> tuple[np.ndarray,np.ndarray]:
    """Translation of ``gull1.f90``; returned arrays contain logarithmic g values."""
    if n < 1 or n > 99: raise ValueError("gull1 requires 1<=n<=99")
    dn=float(n); r=float(rs); pi=math.pi
    # Fortran fact(2*n-1) returns log factorial.
    f1=math.lgamma(2*n)
    g0=.5*math.log(pi/2)+math.log(8*dn)+dn*math.log(4*dn)-f1
    gu=np.zeros(100,float); gl=np.zeros(100,float)
    if r == 0: gu[n-1]=g0-2*dn
    else:
        ss=math.sqrt(r); gu[n-1]=g0-2*math.atan(dn*ss)/ss-.5*math.log(max(1-math.exp(-2*pi/ss),1e-300))
    gu[n-1]=math.exp(gu[n-1]); fn=1e-300/max(gu[n-1],1e-300); gu[n-1]*=fn
    if n == 1:
        gl[0]=0.0; gu[0]=2*math.log(max(gu[0],1e-300))-math.log(4)-5*math.log(1+r)-2*math.log(fn)
        return gu,gl
    gu[n-2]=(2*dn-1)*(1+dn*dn*r)*dn*gu[n-1]
    gl[n-1]=(1+dn*dn*r)*gu[n-1]/(2*dn)
    gl[n-2]=(2*dn-1)*(4+(dn-1)*(1+dn*dn*r))*gl[n-1]
    for l in range(n-1,2,-1):
        dl=float(l)
        gu[l-2]=(4*dn*dn-4*dl*dl+dl*(2*dl-1)*(1+dn*dn*r))*gu[l-1]-4*dn*dn*(dn-dl)*(dn+dl)*(1+(dl+1)**2*r)*gu[l]
        gl[l-2]=(4*dn*dn-4*(dl-1)**2+(dl-1)*(2*dl-1)*(1+dn*dn*r))*gl[l-1]-4*dn*dn*(dn-dl)*(dn+dl)*(1+(dl-1)**2*r)*gl[l]
    gl[0]=0.0
    if n >= 3:
        gu[0]=(4*dn*dn-16+6*(1+dn*dn*r))*gu[1]-4*dn*dn*(dn-2)*(dn+2)*(1+9*r)*gu[2]
    cn=math.log(dn)-dn*math.log(4*dn*dn)-(2*dn+4)*math.log(1+dn*dn*r)
    gu[0]=cn+math.log(1+r)+2*math.log(max(abs(gu[0]),1e-300))-2*math.log(fn)
    clu=cn+math.log(1+r); cll=cn
    for l in range(1,n):
        dl=float(l)
        clu += math.log(max(4*dn*dn*(dn-dl)*(dn+dl)*(1+(dl+1)**2*r),1e-300))
        cll += math.log(max(4*dn*dn*(dn-dl)*(dn+dl)*(1+(dl-1)**2*r),1e-300))
        gu[l]=clu+2*math.log(max(abs(gu[l]),1e-300))-2*math.log(fn)
        gl[l]=cll+2*math.log(max(abs(gl[l]),1e-300))-2*math.log(fn)
    return gu,gl


def hphotx(energy_above_threshold_ryd: float, ion_charge: int, principal_n: int) -> np.ndarray:
    """Translation of ``hphotx.f90``; cross sections are returned in Mb."""
    en=max(float(energy_above_threshold_ryd),0.0); ic=max(int(ion_charge),1); nq=max(int(principal_n),1)
    rk=math.sqrt(en)/(ic*ic); gu,gl=gull1(nq,rk*rk); cons=.54492*math.acos(0.0)
    out=np.zeros(max(100,nq),float)
    for lm in range(nq):
        theta1=(1+nq*nq*rk*rk)*math.exp(min(700.0,gu[lm])); theta2=(1+nq*nq*rk*rk)*math.exp(min(700.0,gl[lm])) if lm>0 else 0.0
        out[lm]=cons*((lm+1)*theta1+lm*theta2)/(2*lm+1)*nq*nq/(ic*ic)
    return out


def pexs(nmin: int, zc: float, eion_ryd: float, far: float, gam: float, scal: float, energy_ryd: Sequence[float]) -> np.ndarray:
    """Translation of ``pexs.f90``."""
    nmax=30; e=np.asarray(energy_ryd,float); out=np.zeros_like(e)
    if nmin >= nmax or nmin < 1: return out
    x={}; area={}; nres=nmax
    for n in range(nmin,nmax+1):
        x[n]=-(zc/n)**2; area[n]=8.06725*far*(nmin**3)/(n**3)
        if n>nmin and x[n]-x[n-1] > gam/2: nres=n
    shifted=e-eion_ryd; xmin=x[nmin]-30*gam; xres=x[nres]
    jmin=max(0,min(int(np.searchsorted(shifted,xmin)-1),len(e)-1)); jres=max(jmin,min(int(np.searchsorted(shifted,xres)-1),len(e)-1)); jmax=max(jmin,min(int(np.searchsorted(shifted,0.0)-1),len(e)-1))
    for n in range(nmin,nmax+1):
        for j in range(jmin,jres+1):
            out[j]+=area[n]/math.pi*gam/2/((shifted[j]-x[n])**2+(gam/2)**2)+area[n]/math.pi*gam/2/((abs(shifted[j])-x[n])**2+(gam/2)**2)
    if jres < jmax: out[jres+1:jmax+1]=out[jres]
    return scal*out


def calt70(reals: Sequence[float], integers: Sequence[int], temp_k: float, density: float, threshold_ryd: float) -> tuple[float,np.ndarray,np.ndarray,dict]:
    """Translation of ``calt70.f90`` including density/temperature interpolation."""
    rr=np.asarray(reals,float); ii=list(int(v) for v in integers)
    if len(ii)<3: raise ValueError("calt70 requires nden,ntem,nxs")
    nden,ntem,nxs=ii[:3]
    required=nden+ntem+nden*ntem+2*nxs
    if nden<1 or ntem<2 or nxs<1 or rr.size<required: raise ValueError("short calt70 packed record")
    dens=rr[:nden].copy(); temps=rr[nden:nden+ntem]; table=rr[nden+ntem:nden+ntem+nden*ntem].reshape(nden,ntem)
    rne=math.log10(max(density,1e-300)); rte=math.log10(max(temp_k,1e-300)); rne=min(max(rne,dens[0]),dens[-1]); rte=min(max(rte,temps[0]),temps[-1])
    vals=np.asarray([np.interp(rte,temps,row) for row in table])
    if nden>2 and dens[1] < rne < dens[-2]:
        mid=max(1,min(int(np.searchsorted(dens,rne)-1),nden-2)); idx=[mid-1,mid,mid+1]; co=np.polyfit(dens[idx],vals[idx],2); logrec=float(np.polyval(co,rne))
    else: logrec=float(np.interp(rne,dens,vals))
    rec=10.0**logrec
    start=nden+ntem+nden*ntem; xs_e=rr[start:start+2*nxs:2].copy(); xs=rr[start+1:start+2*nxs:2].copy()
    alpha=milne(temp_k,xs_e,xs,threshold_ryd); scale=rec/(1e-24+alpha); xs=np.minimum(np.maximum(xs*scale,0.0),1e6)
    keep=np.where(xs>xs[0]*1e-6)[0]; end=(int(keep[-1])+1) if keep.size else 1
    return rec,xs_e[:end],xs[:end],{"log10_recombination":logrec,"milne_alpha":alpha,"scale":scale,"nden":nden,"ntem":ntem,"nxs":nxs}


def _interp_hunt(n: int, x: Sequence[float], y: Sequence[float], value: float) -> float:
    n=max(1,min(int(n),len(x),len(y))); xa=np.asarray(x[:n],float); ya=np.asarray(y[:n],float)
    if n==1: return float(ya[0])
    return float(np.interp(value,xa,ya,left=ya[0],right=ya[-1]))


def calc_sampson_p(om: Sequence[float], z: int, temp_k: float) -> float:
    dE,a,z2s,c0,cr,cr1,r,s=list(om[:8]); y=dE/(KBOLTZ_KEV_K*temp_k); a1=a+1; e1=exintn(y,1); er=exintn(a1*y,int(r)); er1=exintn(a1*y,int(r+1)); term=cr*er/a1**(r-1)+cr1*er1/a1**r
    z2gamma=c0+1.333*z2s*e1*expo(y)+(y*expo(a1*y)*term if term>0 else 0.0); return z2gamma/max((z-s)**2,1e-300)


def calc_sampson_h(om: Sequence[float], z: int, temp_k: float) -> float:
    dE,z2s,a,c0,c1,c2,csw=list(om[:7]); y=dE/(KBOLTZ_KEV_K*temp_k); a1=a+1; e1=exintn(y,1); er=exintn(a1*y,1); er1=exintn(a1*y,2,er); term=c1*er+c2*er1/a1
    val=c0+1.333*z2s*e1*expo(y)+(y*expo(a1*y)*term if term>0 else 0.0); return val*2*csw/max(z*z,1e-300)


def calc_sampson_s(om: Sequence[float], z: int, temp_k: float) -> float:
    dE,a1g,a1eg,z2sh,a2,c0,c1,c2,a2e,cere,cere1,re,s,se=list(om[:14]); y=dE/(KBOLTZ_KEV_K*temp_k)
    aa=a2+1; e1=exintn(y,1); er=exintn(aa*y,1); er1=exintn(aa*y,2,er); term=c1*er+c2*er1/aa; z2g=c0+1.333*z2sh*e1*expo(y)+(y*expo(aa*y)*term if a1g!=0 and term>0 else 0.0)
    aa=a2e+1; er=exintn(aa*y,int(re)); er1=exintn(aa*y,int(re)+1); term=cere*er/aa**(re-1)+cere1*er1/aa**re; z2ge=y*expo(aa*y)*term if a1eg!=0 and term>0 else 0.0
    return a1g*z2g/max((z-s)**2,1e-300)+a1eg*z2ge/max((z-se)**2,1e-300)


def calc_kato(kind: int, par: Sequence[float], z: int, temp_k: float) -> float:
    dE,A,B,C,D,E,P,Q,X1=list(par[:9]); y=dE/(KBOLTZ_KEV_K*temp_k)
    if kind==1:
        e1=exintn(y,1); term1=A/y+C+D/2*(1-y); term2=B-C*y+D/2*y*y+E/y; return y*(term1+expo(y)*e1*term2)
    e1=exintn(X1*y,1); term3=expo(y*(1-X1)); term1=A/y+C/X1+D/2*(1/X1**2-y/X1)+(E/y)*math.log(X1); term2=expo(y*X1)*e1*(B-C*y+D*y*y/2+E/y); return y*term3*(term1+term2)+P*((1+1/y)-term3*(X1+1/y))+Q*(1-term3)


def calc_maxwell_rates(coll_type: int,min_t: float,max_t: float,tarr: Sequence[float],om: Sequence[float],de_kev: float,temp_k: float,z: int,degl: float,degu: float) -> tuple[float,float,float,dict]:
    """Python translation of ``calc_maxwell_rates.f90``.

    The original source supports analytical CHIANTI/Sampson/Kato families and
    a grid of interpolation-code ranges.  Proton collision strengths remain
    source-defined as unimplemented (zero rates), while proton *rate*
    coefficients are used directly as in the Fortran routine.
    """
    if de_kev<=0 or temp_k<=0 or temp_k<min_t or temp_k>max_t: return 0.0,0.0,0.0,{"status":"outside_range"}
    chi=de_kev/(KBOLTZ_KEV_K*temp_k); chi_inv=1/max(chi,1e-300); ups=0.0; rate=0.0; calc=None; om=list(float(v) for v in om); tarr=list(float(v) for v in tarr)
    ct=int(coll_type)
    if ct==1:
        a,b,c,d,e=(om+[0]*5)[:5]; e2=exintn(chi,2); ups=a+b*chi*e2+c*chi*(1-chi*e2)+d*(chi/2)*(1-chi*(1-chi*e2))+e*e2; calc="e_ups"
    elif 11<=ct<=16:
        vals=(om+[0]*5)[:5]; cc=max(vals[0],1e-300); st=(1-math.log(cc)/math.log(chi_inv+cc)) if ct in (11,14) else chi_inv/(chi_inv+cc); ups=natural_cubic_spline((0,.25,.5,.75,1),vals,st)
        if ct==11: ups*=math.log(chi_inv+math.e)
        elif ct==13: ups/=chi_inv+1
        elif ct==14: ups*=math.log(chi_inv+cc)
        elif ct==15: ups/=chi_inv
        elif ct==16: ups=10**ups
        calc="e_ups" if ct!=16 else "p_ups"
    elif 21<=ct<=26:
        ns=int(om[0]) if om else 0; cc=max(om[1] if len(om)>1 else 1.0,1e-300); vals=om[2:2+ns]; grid=(0,.25,.5,.75,1) if ns==5 else (0,.125,.25,.375,.5,.675,.8,.925,1); st=(1-math.log(cc)/math.log(chi_inv+cc)) if ct in (21,24) else chi_inv/(chi_inv+cc); ups=natural_cubic_spline(grid,vals,st)
        if ct==21: ups*=math.log(chi_inv+math.e)
        elif ct==23: ups/=chi_inv+1
        elif ct==24: ups*=math.log(chi_inv+cc)
        elif ct==25: ups/=chi_inv
        elif ct==26: ups=10**ups
        calc="e_ups" if ct!=26 else "p_ups"
    elif ct==31: ups=calc_sampson_s(om,z,temp_k); calc="e_ups"
    elif ct==32: ups=calc_sampson_p(om,z,temp_k); calc="e_ups"
    elif ct==33: ups=calc_sampson_h(om,z,temp_k); calc="e_ups"
    elif ct==41: ups=calc_kato(1,om,z,temp_k); calc="e_ups"
    elif ct==42: ups=calc_kato(2,om,z,temp_k); calc="e_ups"
    elif ct==1001:
        a,b,c=(om+[0]*3)[:3]; logt=math.log10(temp_k); rate=.8*10**(a+b*logt+c*logt*logt) if len(om)>=4 and om[2]<logt<om[3] else 0.0; calc="p_rate"
    else:
        ranges=((100,"e_ups","all"),(150,"e_ups","open"),(500,"e_ups","inc_min"),(550,"e_ups","inc_max"),(200,"p_ups","all"),(250,"p_ups","open"),(600,"p_ups","inc_min"),(650,"p_ups","inc_max"),(300,"e_rate","all"),(350,"e_rate","open"),(700,"e_rate","inc_min"),(750,"e_rate","inc_max"),(400,"p_rate","all"),(450,"p_rate","open"),(800,"p_rate","inc_min"),(850,"p_rate","inc_max"))
        hit=False
        for base,kind,bounds in ranges:
            if base<=ct<=base+20:
                n=ct-base; allowed=(bounds=="all" or bounds=="open" and min_t<temp_k<max_t or bounds=="inc_min" and temp_k<max_t or bounds=="inc_max" and temp_k>min_t)
                val=_interp_hunt(n,tarr,om,temp_k) if allowed else 0.0
                if kind.endswith("ups"): ups=val
                else: rate=val
                calc=kind; hit=True; break
        if not hit: return 0.0,0.0,0.0,{"status":"undefined_collision_type"}
    ups=max(ups,0.0); rate=max(rate,0.0)
    if calc=="e_ups":
        if chi>=200: return 0.0,0.0,ups,{"status":"chi_too_large","calc_type":calc}
        exc=UPSILON_COLL_COEFF*ups*math.exp(-chi)/(math.sqrt(temp_k)*max(degl,1e-300)); dex=UPSILON_COLL_COEFF*ups/(math.sqrt(temp_k)*max(degu,1e-300))
    elif calc=="p_ups": exc=dex=0.0
    else: exc=rate; dex=rate*expo(chi)*degl/max(degu,1e-300)
    return exc,dex,ups,{"status":"evaluated","calc_type":calc,"chi":chi}


__all__=["expo","exintn","natural_cubic_spline","phextrap","bkhsgo","milne","gull1","hphotx","pexs","calt70","calc_maxwell_rates"]
