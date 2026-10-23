# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Original SAD/No SAD endpoint: additive clinical figures, no model changes.

Statistical graphics use the existing Anaconda environment. TIFF conversion and
verification use the bundled Python/Pillow runtime. Source files are read only.
"""
from pathlib import Path
from math import sqrt
import hashlib
import json
import subprocess
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch, Rectangle

ROOT = _sad_private_path("clinical_support", "binary_correction")
WORK = ROOT.parents[1]
INPUT = _sad_private_path('clinical_support','descriptive_analysis','linked_descriptive_cohort.csv')
RISK_INPUT = _sad_private_path('eicu_validation','reference_sources','identified_frozen_risk_scores.csv')
EXPORT = _sad_private_path('mimic_exports')
OUT = ROOT/'outputs'
ASSETS = ROOT/'figure_assets'
OUT.mkdir(parents=True,exist_ok=True)
ASSETS.mkdir(exist_ok=True)
BUNDLED = sys.executable
R = ['Low','Intermediate','High']
S = ['Neither recorded','MV recorded only','Vasopressor recorded only','Both recorded']
O = ['SAD','No SAD']
COL = {'Low':'#27978B','Intermediate':'#4C78A8','High':'#D46B57'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'svg.fonttype':'none',
    'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})

def sha256(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):
            h.update(chunk)
    return h.hexdigest()

def wilson(k,n):
    z=1.959963984540054
    p=k/n
    a=1+z*z/n
    center=(p+z*z/(2*n))/a
    half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/a
    return max(0,center-half),min(1,center+half)

def write_csv(d,name):
    d.to_csv(ROOT/name,index=False,encoding='utf-8-sig')

linked = pd.read_csv(INPUT,low_memory=False)
assert linked.stay_id.is_unique
assert linked.legacy_sad_7days.notna().all()
assert set(linked.legacy_sad_7days.unique()) == {0,1}
linked['legacy_sad_7days'] = linked.legacy_sad_7days.astype(int)
risk = pd.read_csv(RISK_INPUT,low_memory=False)
assert risk.stay_id.is_unique
assert len(linked)==len(risk)==17851
audits=[]
for p in [RISK_INPUT,EXPORT/'sad_cohort.csv',EXPORT/'sad_outcome_summary.csv']:
    src=pd.read_csv(p,usecols=['stay_id','legacy_sad_7days'])
    assert src.stay_id.is_unique
    check=linked[['stay_id','legacy_sad_7days','split']].merge(src,on='stay_id',how='left',
        suffixes=('_linked','_source'),validate='one_to_one',indicator=True)
    matched=check._merge.eq('both')
    missing=check.legacy_sad_7days_source.isna()
    unequal=check.legacy_sad_7days_linked.ne(check.legacy_sad_7days_source)
    assert matched.all() and not missing.any() and not unequal.any(), str(p)
    audits.append({'source':str(p),'matched_linked_rows':int(matched.sum()),
        'missing_labels':int(missing.sum()),'label_mismatches':int(unequal.sum()),
        'test_rows':int(check.split.eq('test').sum()),
        'test_label_mismatches':int(unequal[check.split.eq('test')].sum()),'sha256':sha256(p)})
check=linked[['stay_id','risk_group','split','risk_probability_frozen14']].merge(
    risk[['stay_id','risk_group','split','risk_probability_frozen14']],on='stay_id',
    suffixes=('_linked','_source'),validate='one_to_one')
assert check.risk_group_linked.eq(check.risk_group_source).all()
assert check.split_linked.eq(check.split_source).all()
prob_error=float((check.risk_probability_frozen14_linked-check.risk_probability_frozen14_source).abs().max())
assert prob_error<1e-14
d=linked[linked.split.eq('test')].copy()
assert len(d)==3571 and d.legacy_sad_7days.sum()==467
assert d.legacy_sad_7days.eq(0).sum()==3104
assert d.risk_group.isin(R).all() and d.support_group.isin(S).all()
d['binary_outcome']=np.where(d.legacy_sad_7days.eq(1),'SAD','No SAD')
assert d.binary_outcome.notna().all()

rows=[]
for s in S:
    for r in R:
        x=d[d.support_group.eq(s)&d.risk_group.eq(r)]
        n=len(x);k=int(x.legacy_sad_7days.sum());lo,hi=wilson(k,n)
        rows.append({'support_group':s,'risk_group':r,'n_all':n,'n_positive':k,
            'n_negative':n-k,'proportion':k/n,'ci95_low':lo,'ci95_high':hi})
rates=pd.DataFrame(rows)
write_csv(rates,'binary_support_rates.csv')
assert rates.n_all.sum()==3571 and rates.n_positive.sum()==467 and rates.n_negative.sum()==3104

flows=d.groupby(['risk_group','support_group','binary_outcome'],observed=True).size().rename('n').reset_index()
idx=pd.MultiIndex.from_product([R,S,O],names=['risk_group','support_group','binary_outcome'])
flows=flows.set_index(['risk_group','support_group','binary_outcome']).reindex(idx,fill_value=0).reset_index()
write_csv(flows,'binary_sankey_flows.csv')
triplets=flows[flows.n.gt(0)].set_index(['risk_group','support_group','binary_outcome']).n.to_dict()
assert sum(triplets.values())==len(d)

# Independent crosstabs check each pair/layer, not just a common grand total.
pair_risk_support=pd.crosstab(d.risk_group,d.support_group).reindex(index=R,columns=S,fill_value=0)
pair_support_outcome=pd.crosstab(d.support_group,d.binary_outcome).reindex(index=S,columns=O,fill_value=0)
for r in R:
    for s in S:
        assert int(pair_risk_support.loc[r,s])==sum(n for t,n in triplets.items() if t[0]==r and t[1]==s)
for s in S:
    for o in O:
        assert int(pair_support_outcome.loc[s,o])==sum(n for t,n in triplets.items() if t[1]==s and t[2]==o)
node_counts={c:{str(k):int(v) for k,v in d[c].value_counts().items()} for c in ['risk_group','support_group','binary_outcome']}
assert all(sum(x.values())==3571 for x in node_counts.values())

risk_summary=[]
for r in R:
    x=d[d.risk_group.eq(r)];n=len(x);k=int(x.legacy_sad_7days.sum());lo,hi=wilson(k,n)
    risk_summary.append({'risk_group':r,'n_all':n,'n_positive':k,'n_negative':n-k,
        'proportion':k/n,'ci95_low':lo,'ci95_high':hi,
        'fraction_of_test':n/len(d),'fraction_of_all_SAD':k/467})
comparisons=[]
for s in S:
    z=rates[rates.support_group.eq(s)].set_index('risk_group')
    lo=z.loc['Low'];hi=z.loc['High']
    comparisons.append({'support_group':s,'low_events':int(lo.n_positive),'low_total':int(lo.n_all),
        'low_proportion':float(lo.proportion),'high_events':int(hi.n_positive),'high_total':int(hi.n_all),
        'high_proportion':float(hi.proportion),'high_minus_low_percentage_points':float(100*(hi.proportion-lo.proportion)),
        'high_to_low_observed_proportion_ratio':float(hi.proportion/lo.proportion),
        'monotonic_low_to_high':bool(z.loc['Low','proportion']<=z.loc['Intermediate','proportion']<=z.loc['High','proportion'])})
write_csv(pd.DataFrame(risk_summary),'binary_risk_group_summary.csv')
write_csv(pd.DataFrame(comparisons),'binary_support_high_low_differences.csv')

def save(fig,num):
    # Preserve the specified 7.2-inch canvas; no tight-bbox resize.
    png=OUT/f'Figure_{num}.png';svg=OUT/f'Figure_{num}.svg'
    fig.savefig(png,dpi=300)
    fig.savefig(svg)
    highres=ASSETS/f'Figure_{num}_600dpi.png'
    fig.savefig(highres,dpi=600)
    converter='from PIL import Image;import sys;im=Image.open(sys.argv[1]).convert("RGB");im.save(sys.argv[2],compression="tiff_lzw",dpi=(600,600));im.close()'
    subprocess.run([BUNDLED,'-c',converter,str(highres),str(OUT/f'Figure_{num}.tif')],check=True)
    plt.close(fig)

keys=[R,S,O];cols=['risk_group','support_group','binary_outcome']
gap=.035;usable_height=.86
max_nodes=max(len(x) for x in keys)
scale=(usable_height-gap*(max_nodes-1))/len(d)
layouts=[]
for col,ks in zip(cols,keys):
    cnt=d[col].value_counts().to_dict()
    total=sum(cnt.values())*scale+gap*(len(ks)-1)
    top=(1+total)/2;positions={}
    for key in ks:
        h=cnt.get(key,0)*scale;positions[key]=(top-h,top);top-=h+gap
    layouts.append(positions)
orders=[sorted(triplets,key=lambda z:(R.index(z[0]),S.index(z[1]),O.index(z[2]))),
    sorted(triplets,key=lambda z:(S.index(z[1]),R.index(z[0]),O.index(z[2]))),
    sorted(triplets,key=lambda z:(O.index(z[2]),R.index(z[0]),S.index(z[1])))]
slots=[{} for _ in cols]
for j,order in enumerate(orders):
    cursor={k:v[0] for k,v in layouts[j].items()}
    for t in order:
        k=t[j];h=triplets[t]*scale;slots[j][t]=(cursor[k],cursor[k]+h);cursor[k]+=h
    for k,(lo,hi) in layouts[j].items():
        assert 0<=lo<=hi<=1
        assert abs(cursor[k]-hi)<1e-12
        assigned=sum(slots[j][t][1]-slots[j][t][0] for t in order if t[j]==k)
        assert abs(assigned-(hi-lo))<1e-12

fig,ax=plt.subplots(figsize=(7.2,4.65))
fig.subplots_adjust(left=.02,right=.98,bottom=.04,top=.95)
ax.set_xlim(-.23,1.32);ax.set_ylim(-.025,1.07);ax.axis('off')
xs=[0,.51,1.02];w=.025
for t,n in triplets.items():
    for j in [0,1]:
        a=xs[j]+w;b=xs[j+1];mid=(a+b)/2
        lo0,hi0=slots[j][t];lo1,hi1=slots[j+1][t]
        verts=[(a,lo0),(mid,lo0),(mid,lo1),(b,lo1),(b,hi1),(mid,hi1),(mid,hi0),(a,hi0),(a,lo0)]
        codes=[MPath.MOVETO,MPath.CURVE4,MPath.CURVE4,MPath.CURVE4,MPath.LINETO,MPath.CURVE4,MPath.CURVE4,MPath.CURVE4,MPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MPath(verts,codes),facecolor=COL[t[0]],alpha=.29,edgecolor='none'))
names={S[0]:'Neither recorded',S[1]:'MV only',S[2]:'Vasopressor only',S[3]:'Both recorded'}
for j,(layout,ks) in enumerate(zip(layouts,keys)):
    for i,k in enumerate(ks):
        lo,hi=layout[k];count=int(d[cols[j]].eq(k).sum())
        color=COL[k] if j==0 else ('#64748B' if j==1 else ['#B35B4B','#789F9A'][i])
        ax.add_patch(Rectangle((xs[j],lo),w,hi-lo,facecolor=color,edgecolor='none'))
        label=f'{names.get(k,k)}\nn = {count:,}'
        if j==0:
            ax.text(xs[j]-.023,(lo+hi)/2,label,ha='right',va='center',fontsize=8.3,color='#233044')
        elif j==1:
            ax.text(xs[j]+w/2,(lo+hi)/2,label,ha='center',va='center',fontsize=7.7,color='#233044',
                bbox={'facecolor':'white','edgecolor':'none','pad':1.5,'alpha':.94})
        else:
            ax.text(xs[j]+w+.022,(lo+hi)/2,label,ha='left',va='center',fontsize=8.3,color='#233044')
for x,title in zip(xs,['Model risk','Support at diagnosis','7-day outcome']):
    ax.text(x+w/2,1.035,title,ha='center',va='bottom',fontsize=8.8,fontweight='bold',color='#233044')
save(fig,4)

fig,axes=plt.subplots(2,2,figsize=(7.2,5.8),sharey=True)
titles=['A  Neither recorded','B  Mechanical ventilation only','C  Vasopressor only','D  Both recorded']
for ax,s,title in zip(axes.flat,S,titles):
    block=rates[rates.support_group.eq(s)].set_index('risk_group').loc[R]
    for j,r in enumerate(R):
        row=block.loc[r];p=row.proportion
        ax.errorbar(j,100*p,yerr=np.array([[p-row.ci95_low],[row.ci95_high-p]])*100,
            fmt='o',markersize=4.5,color=COL[r],capsize=3,elinewidth=1.25)
        ax.text(j,-.19,f'{int(row.n_positive)}/{int(row.n_all)}',ha='center',va='top',
            transform=ax.get_xaxis_transform(),fontsize=7.8,color='#526071')
    ax.set_title(title,loc='left',fontsize=8.5,fontweight='bold',pad=7)
    ax.set_xticks(range(3),R,fontsize=7.8);ax.set_xlim(-.5,2.5);ax.set_ylim(0,55)
    ax.set_yticks([0,10,20,30,40,50]);ax.tick_params(axis='y',labelsize=7.5)
    ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    ax.spines['left'].set_color('#ABB4BF');ax.spines['bottom'].set_color('#ABB4BF')
for ax in axes[:,0]:
    ax.set_ylabel('Observed SAD incidence (%)',fontsize=8.2)
fig.subplots_adjust(left=.105,right=.99,top=.94,bottom=.14,hspace=.66,wspace=.15)
fig.text(.5,.035,'Values below risk groups indicate SAD events / total patients.',
    ha='center',va='center',fontsize=7.8,color='#526071')
save(fig,5)

# Inspect generated TIFFs using the bundled Pillow runtime, never system PIL.
asset_script='''from PIL import Image
from pathlib import Path
import json,sys
out=Path(sys.argv[1]);checks=[]
for num in [4,5]:
 p=out/f"Figure_{num}.tif"
 with Image.open(p) as im:
  im.load()
  row={"file":str(p),"size":list(im.size),"mode":im.mode,"dpi":[float(v) for v in im.info.get("dpi",())],"compression_tag":int(im.tag_v2[259])}
  assert im.size[0]==4320
  assert int(im.tag_v2[259])==5
  assert im.mode=="RGB"
  assert all(abs(float(v)-600)<.01 for v in im.info["dpi"])
  checks.append(row)
print(json.dumps(checks))
'''
assets=json.loads(subprocess.check_output([BUNDLED,'-c',asset_script,str(OUT)],text=True))
for num in [4,5]:
    svg=(OUT/f'Figure_{num}.svg').read_text(encoding='utf-8')
    assert 'No valid' not in svg and 'Unknown' not in svg and 'Observed negative only' not in svg
    if num==4:
        assert '>SAD<' in svg and '>No SAD<' in svg
    else:
        assert 'Observed SAD incidence (%)' in svg

summary={'endpoint':'original study legacy_sad_7days, unchanged',
    'population':'independent test set','n_all':3571,'n_positive':467,'n_negative':3104,'n_unknown':0,
    'risk_group_and_support_group_unchanged':True,'model_retrained':False,'risk_cutpoints_changed':False,
    'input':str(INPUT),'input_sha256':sha256(INPUT),'label_audit_all_linked_rows':audits,
    'risk_probability_max_absolute_difference_from_identified_scores':prob_error,
    'risk_group_summary':risk_summary,'support_high_low_comparisons':comparisons,
    'node_counts':node_counts,'sankey_flow_total_each_transition':3571,
    'sankey_pairwise_crosstab_and_slot_conservation_passed':True,
    'sankey_max_nodes':max_nodes,'sankey_node_gap':gap,'sankey_units_per_patient':scale,
    'figure_width_inches':7.2,'figure_assets':assets,
    'statistics_graphics_runtime':sys.executable,'tiff_conversion_runtime':BUNDLED,
    'original_figures_and_source_exports_modified':False,'new_treatment_effects_estimated':False}
(ROOT/'binary_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
print(rates.to_string(index=False))
print(json.dumps({'counts':{'total':3571,'SAD':467,'No SAD':3104},'risk_groups':risk_summary,
    'high_low':comparisons,'label_sources_agree':True,'flow_checks_passed':True},ensure_ascii=False,indent=2))
print('Exported Figure 4/5: PNG, SVG and 600-dpi LZW TIFF in '+str(OUT))
