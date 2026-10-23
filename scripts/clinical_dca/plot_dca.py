# Local data and generated outputs stay outside the source repository.
from pathlib import Path
import os
_SAD_REPO = Path(__file__).resolve().parents[2]
_SAD_PRIVATE = Path(os.environ.get("SAD_PRIVATE_ROOT", str(_SAD_REPO.parent / "study_code_and_data" / "final_analysis"))).expanduser().resolve()
def _sad_private_path(*parts):
    return _SAD_PRIVATE.joinpath(*parts)

"""Publication graphics for DCA and paired incremental net benefit."""
from pathlib import Path
import json
import subprocess
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ROOT=_sad_private_path("clinical_dca")
for _folder in ["data", "results", "figures", "figure_assets", "qa", "notes"]:
    (ROOT/_folder).mkdir(parents=True, exist_ok=True)
OUT=ROOT/'figures'/'revision_30pct_20261022'
ASSETS=ROOT/'figure_assets'/'revision_30pct_20261022'
ASSETS.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
import sys
BUNDLED=sys.executable
curves=pd.read_csv(ROOT/'results'/'decision_curves_primary_range.csv')
delta=pd.read_csv(ROOT/'results'/'net_benefit_differences.csv')
COL={'model':'#167D8D','sofa':'#8D62A8','mv':'#D47D36','all':'#8B929A','none':'#30363D'}
DIFFCOL={'sofa':'#3E6DA5','mv':'#CD7136'}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'svg.fonttype':'none',
    'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False,
    'axes.labelcolor':'#26313D','text.color':'#26313D','xtick.color':'#26313D','ytick.color':'#26313D'})

PLOT_AUDIT=[]

def save(fig,name):
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    assert all(tuple(ax.get_xlim()) == (1.0,30.0) for ax in fig.axes)
    subtitle=[t for t in fig.texts if 'Observed SAD incidence: 13.08%' in t.get_text()]
    assert len(subtitle)==1
    for t in subtitle:
        bb=t.get_window_extent(renderer)
        assert bb.x0>=0 and bb.x1<=fig.bbox.width and bb.y0>=0 and bb.y1<=fig.bbox.height
    assert all(0<=tick<=30 for ax in fig.axes for tick in ax.get_xticks())
    PLOT_AUDIT.append({'name':name,'x_limits':[list(ax.get_xlim()) for ax in fig.axes],'subtitle':subtitle[0].get_text()})
    fig.savefig(OUT/f'{name}.png',dpi=300)
    fig.savefig(OUT/f'{name}.svg')
    high=ASSETS/f'{name}_600dpi.png'
    fig.savefig(high,dpi=600)
    convert='from PIL import Image; import sys; Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2],compression="tiff_lzw",dpi=(600,600))'
    subprocess.run([BUNDLED,'-c',convert,str(high),str(OUT/f'{name}.tif')],check=True)
    plt.close(fig)

def style(ax):
    ax.set_xlim(1,30)
    ax.set_xticks([1,5,10,15,20,25,30])
    ax.set_xlabel('Risk threshold (%)',fontsize=8.2,labelpad=6)
    ax.grid(axis='y',color='#CFD5DC',alpha=.6,linewidth=.55)
    ax.set_axisbelow(True)
    ax.spines['left'].set_color('#AEB6BF');ax.spines['bottom'].set_color('#AEB6BF')
    ax.tick_params(labelsize=7.8,length=3)

def draw_dca(ax,compact=False):
    labels={'model':'Frozen 14-predictor model','sofa':'ICU first-day SOFA only',
            'mv':'MV only','all':'Prioritize all','none':'Prioritize none'}
    for name,linestyle in [('all',(0,(2,2))),('none',(0,(5,2))),('sofa','-'),('mv',(0,(4,2))),('model','-')]:
        b=curves[curves.strategy.eq(name)].sort_values('threshold')
        ax.plot(b.threshold*100,b.net_benefit_per_100,label=labels[name],color=COL[name],
                lw=1.75 if name=='model' else 1.3,linestyle=linestyle,zorder=4 if name=='model' else 3)
    ax.set_ylim(-4,14)
    ax.set_yticks([-4,0,4,8,12])
    ax.set_ylabel('Net benefit per 100 patients',fontsize=8.2)
    handles,lab=ax.get_legend_handles_labels()
    order=[lab.index(labels[k]) for k in ['model','sofa','mv','all','none']]
    ax.legend([handles[i] for i in order],[lab[i] for i in order],frameon=False,
              loc='upper right',fontsize=6.6 if compact else 8.0,handlelength=2.3,
              labelspacing=.55,borderaxespad=.2)
    ax.text(.54,.045,'“Prioritize all” continues\nbelow the displayed range.',
            transform=ax.transAxes,fontsize=6.4 if compact else 7.4,color='#757D86',va='bottom')
    style(ax)

def draw_delta(ax,compact=False):
    for name,linestyle in [('sofa','-'),('mv',(0,(4,2)))]:
        b=delta[delta.comparator.eq(name)].sort_values('threshold')
        x=b.threshold.to_numpy()*100
        ax.fill_between(x,b.ci95_low_per_100,b.ci95_high_per_100,color=DIFFCOL[name],alpha=.14,linewidth=0)
        ax.plot(x,b.delta_net_benefit_per_100,color=DIFFCOL[name],linestyle=linestyle,lw=1.6,
                label='Model − '+('SOFA only' if name=='sofa' else 'MV only'))
    ax.axhline(0,color='#3C4651',lw=.9,linestyle=(0,(3,3)))
    ax.set_ylim(-2.4,4.0)
    ax.set_yticks([-2,-1,0,1,2,3,4])
    ax.set_ylabel('Net benefit difference per 100 patients',fontsize=8.2)
    ax.legend(frameon=False,loc='upper right',fontsize=7 if compact else 8.5,handlelength=2.5)
    style(ax)

fig,axes=plt.subplots(1,2,figsize=(7.2,4.6))
fig.subplots_adjust(left=.08,right=.985,bottom=.23,top=.80,wspace=.35)
draw_dca(axes[0],True);draw_delta(axes[1],True)
axes[0].set_title('A  Decision curve analysis',loc='left',fontsize=9.2,fontweight='bold',pad=10)
axes[1].set_title('B  Incremental net benefit',loc='left',fontsize=9.2,fontweight='bold',pad=10)
fig.suptitle('Clinical net benefit in the independent test set',fontsize=11.2,fontweight='bold',y=.965)
fig.text(.5,.895,'Original SAD outcome · 3,571 patients · 467 events · Observed SAD incidence: 13.08%',ha='center',fontsize=8.4,color='#5C6875')
fig.text(.08,.11,'SOFA: ICU first-day score. MV: original pre-diagnosis ventilation indicator.',fontsize=7.1,color='#55616E')
fig.text(.08,.069,'Decision: prioritize additional assessment / preventive care; routine assessment remains for all.',fontsize=7.1,color='#55616E')
fig.text(.08,.028,'Exploratory thresholds; training-only comparators. Shading: 95% pointwise CI.',fontsize=7.1,color='#55616E')
save(fig,'Figure_6')

for kind,func,title in [('DCA',draw_dca,'Decision curve analysis'),('DeltaNB',draw_delta,'Incremental net benefit versus SOFA and MV')]:
    fig,ax=plt.subplots(figsize=(6.5,4.8))
    fig.subplots_adjust(left=.13,right=.97,bottom=.23,top=.80)
    func(ax,False)
    fig.suptitle(title,fontsize=12,fontweight='bold',y=.97)
    fig.text(.5,.89,'Independent test set: 3,571 patients, 467 SAD events · Observed SAD incidence: 13.08%',ha='center',fontsize=9,color='#5C6875')
    fig.text(.13,.105,'SOFA: ICU first-day score. MV: original pre-diagnosis indicator.',fontsize=7.9,color='#55616E')
    fig.text(.13,.06,'Decision: prioritize additional care; routine assessment remains for all.',fontsize=7.9,color='#55616E')
    footer='Exploratory thresholds; training-only comparators.'
    if kind=='DeltaNB':footer+=' Shading: 95% pointwise CI.'
    fig.text(.13,.019,footer,fontsize=7.9,color='#55616E')
    save(fig,kind+'_model_vs_SOFA_MV')


(ROOT/'qa'/'plot_display_revision_20261022.json').write_text(json.dumps(PLOT_AUDIT,indent=2),encoding='utf-8')
print('Exported combined A/B and two individual panels, each as PNG, SVG and 600-dpi TIFF.')
