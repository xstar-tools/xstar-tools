#include <fitsio.h>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

struct Rec { int dt; int rt; std::vector<double> r; std::vector<long long> i; std::string c; };
static void check(int s,const char* w){if(!s)return;char t[FLEN_STATUS]{};fits_get_errstatus(s,t);throw std::runtime_error(std::string(w)+": "+t);} 
static std::string ion_name(int z,int stage){
    const char* symbol = z==1 ? "h" : (z==2 ? "he" : (z==12 ? "mg" : "el"));
    return std::string(symbol)+"_"+std::to_string(stage);
}
static void add_element(std::vector<Rec>& v,int z,int stages){
    v.push_back({0,11,{}, {z}, z==1?"h":(z==2?"he":"mg")});
    for(int stage=1;stage<=stages;++stage){
        v.push_back({0,12,{}, {stage}, ion_name(z,stage)});
        const double ionpot = stage<stages ? 10.0*z*stage : 0.0;
        v.push_back({13,13,{0.0,1.0+stage,0.0,ionpot},{1,1,0},"ground"});
        v.push_back({13,13,{std::max(1.0,ionpot),2.0+stage,0.0,ionpot},{2,2,1},"upper"});
        // Type-53 bound-free record.  The first integer is the same-ion
        // destination offset, and the penultimate integer is the bound level.
        v.push_back({53,7,{std::max(1.0,ionpot),1.0e-18,2.0*std::max(1.0,ionpot),5.0e-19},{1,0,1,0},"test rrc"});
        v.push_back({50,4,{1000.0/(z+stage),0.0,1.0e8*(z+stage)},{1,2},"test line"});
        v.push_back({1,3,{1.0e-13/(z+stage),0.25},{},"scalar"});
    }
}
int main(int argc,char**argv){
    if(argc!=2){std::cerr<<"usage: create_multielement_atdb OUTPUT\n";return 64;}
    std::vector<Rec> recs; add_element(recs,1,2); add_element(recs,2,3); add_element(recs,12,3);
    std::vector<long long> p,ii;std::vector<double> rr;std::vector<unsigned char> cc;
    for(std::size_t n=0;n<recs.size();++n){auto&x=recs[n];long long rp=rr.size()+1,ip=ii.size()+1,cp=cc.size()+1;
        p.insert(p.end(),{static_cast<long long>(n+1),x.dt,x.rt,0,static_cast<long long>(x.r.size()),static_cast<long long>(x.i.size()),static_cast<long long>(x.c.size()),rp,ip,cp});
        rr.insert(rr.end(),x.r.begin(),x.r.end());ii.insert(ii.end(),x.i.begin(),x.i.end());cc.insert(cc.end(),x.c.begin(),x.c.end());}
    fitsfile*f=nullptr;int s=0;std::string out="!"+std::string(argv[1]);fits_create_file(&f,out.c_str(),&s);check(s,"create");fits_create_img(f,BYTE_IMG,0,nullptr,&s);check(s,"primary");
    auto table=[&](const char*name,const std::string&form,int type,void*data,long long count,bool length){char*tt[]={const_cast<char*>("DATA")};char*tf[]={const_cast<char*>(form.c_str())};fits_create_tbl(f,BINARY_TBL,1,1,tt,tf,nullptr,const_cast<char*>(name),&s);check(s,"table");fits_write_col(f,type,1,1,1,count,data,&s);check(s,"write");if(length){long long n=recs.size();fits_update_key(f,TLONGLONG,const_cast<char*>("LENGTH"),&n,nullptr,&s);check(s,"length");}};
    table("POINTERS","1QK",TLONGLONG,p.data(),p.size(),true);
    table("REALS","1QD",TDOUBLE,rr.data(),rr.size(),false);
    table("INTEGERS","1QK",TLONGLONG,ii.data(),ii.size(),false);
    table("CHARS","1QB",TBYTE,cc.data(),cc.size(),false);
    fits_close_file(f,&s);check(s,"close");std::cout<<argv[1]<<"\n";return 0;
}
