#!/usr/bin/env python3
"""Run original Probe 2b v1.8 plots and dedicated last-four Stage 4 variable ITI plots."""
import argparse, subprocess, sys, traceback
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

METRICS=[('Hit_Rate','Hit rate (%)',True),('False_Alarm_Rate','False alarm rate (%)',True),('d_prime',"d′",False),('criterion_c','Response bias (c)',False),('Mean_Correct_Touch_Latency_IQRclean_s','Correct touch latency (s)',False),('Mean_Reward_Retrieval_Latency_IQRclean_s','Reward retrieval latency (s)',False)]
GROUPS={'Lecanemab':[('KI2TA-3','PBS'),('KI2TA-3','Lecanemab'),('KI2TA-4','PBS'),('KI2TA-4','Lecanemab')], 'Vaccine':[('KI2TA-3','Sham'),('KI2TA-3','Vaccine'),('KI2TA-4','Sham'),('KI2TA-4','Vaccine')]}
COLORS={'KI2TA-3':'#158b7b','KI2TA-4':'#9363c8'}

def read_csv(path):
    if not path.exists() or path.stat().st_size<3:return pd.DataFrame()
    return pd.read_csv(path,low_memory=False)

def normalize(df):
    if df.empty:return df
    d=df.copy()
    for c in ['Project','Animal_ID','Sex','Genotype','Treatment','Timepoint_Months','Current_ITI_s']:
        if c not in d: raise ValueError(f'Missing Stage 4 required column: {c}')
    d['Sex']=d['Sex'].replace({'M':'Male','F':'Female','male':'Male','female':'Female'})
    d['Genotype']=d['Genotype'].replace({'AppKI2TA-3':'KI2TA-3','AppKI2TA-4':'KI2TA-4','KI2TA3':'KI2TA-3','KI2TA4':'KI2TA-4'})
    for c in ['Timepoint_Months','Current_ITI_s','Baseline_Day_Number','Session_Progress_Decile']:
        if c in d:d[c]=pd.to_numeric(d[c],errors='coerce')
    d=d[d['Current_ITI_s'].isin([2,3]) & d['Timepoint_Months'].isin([6,9,12])].copy()
    return d

def stage_session_filter(df):
    d=normalize(df)
    if d.empty:return d
    if 'Baseline_Day_Number' not in d:raise ValueError('Stage 4 session output lacks Baseline_Day_Number; cannot verify last four sessions.')
    d=d[d['Baseline_Day_Number'].isin([1,2,3,4])].copy()
    if 'SID' in d:
        n=d.groupby(['Project','Animal_ID','Timepoint_Months'])['SID'].nunique()
        if (n>4).any():raise ValueError('More than four unique Stage 4 baseline SIDs within an animal/time point. Verify baseline selections.')
    return d

def animal_means(d,extra=None):
    extra=extra or []
    keys=['Project','Animal_ID','Sex','Genotype','Treatment','Timepoint_Months','Current_ITI_s']+extra
    # Mean of each session metric (animal is statistical unit).
    cols=[name for name,_,_ in METRICS if name in d]
    return d.groupby(keys,as_index=False,dropna=False)[cols].mean() if cols else pd.DataFrame()

def sem(vals):
    a=np.asarray(pd.to_numeric(pd.Series(vals),errors='coerce').dropna(),float)
    return np.std(a,ddof=1)/np.sqrt(len(a)) if len(a)>1 else 0

def base_ax(ax,sex,iti,metric):
    ax.set_title(f'{sex} | both ITIs pooled' if iti is None else f'{sex} | {iti}s ITI',fontsize=10,fontweight='bold')
    ax.text(.95,.87,sex,transform=ax.transAxes,ha='right',alpha=.16,color='#d52f7b' if sex=='Female' else '#2576e2',fontsize=15,weight='bold')
    ax.grid(axis='y',alpha=.18)
    ax.tick_params(labelsize=8)
    ax.set_ylabel(metric,fontsize=9)

def draw_group_bars(ax,d,project,sex,iti,col,percent=False,delta=False):
    q=d[(d.Project==project)&(d.Sex==sex)]
    if not delta:q=q[q.Current_ITI_s==iti]
    groups=GROUPS[project]; vals=[]
    for i,(geno,treatment) in enumerate(groups):
        x=q[(q.Genotype==geno)&(q.Treatment==treatment)]
        z=pd.to_numeric(x[col],errors='coerce').dropna() if col in x else pd.Series(dtype=float)
        if percent:z=z*100
        if z.empty:continue
        color=COLORS[geno]
        hatch='//' if treatment in ('PBS','Sham') else None
        ax.bar(i,z.mean(),width=.65,alpha=.55,color=color,edgecolor=color,hatch=hatch,zorder=2)
        ax.errorbar(i,z.mean(),yerr=sem(z),color='0.20',capsize=3,fmt='none',zorder=4)
        offsets=np.linspace(-.12,.12,len(z)) if len(z)>1 else [0]
        ax.scatter(i+np.asarray(offsets),z,s=15,c=color,edgecolors='white',linewidth=.3,zorder=5)
        vals.extend(z.tolist())
    ax.set_xticks(range(4));ax.set_xticklabels(['E3\nCtrl','E3\nTrt','E4\nCtrl','E4\nTrt'],fontsize=7)
    if vals and not delta and min(vals)>=0:ax.set_ylim(bottom=0)
    if delta and col.startswith('ITI_Delta'):ax.axhline(0,color='0.5',lw=.8)

def panel_pdf(path,d,project,tp,delta=False,pooled=False):
    q=d[(d.Project==project)&(d.Timepoint_Months==tp)].copy()
    if q.empty:return False
    if delta:
        keys=['Project','Animal_ID','Sex','Genotype','Treatment','Timepoint_Months']
        parts=[]
        for col,_,_ in METRICS:
            if col not in q:continue
            w=q.pivot_table(index=keys,columns='Current_ITI_s',values=col,aggfunc='mean')
            if 2 not in w or 3 not in w:continue
            parts.append((w[3]-w[2]).rename(col))
        if not parts:return False
        q=pd.concat(parts,axis=1).reset_index()
    with PdfPages(path) as pdf:
        for start in range(0,len(METRICS),2):
            chunk=METRICS[start:start+2]
            fig,axes=plt.subplots(2,2 if (pooled or delta) else 4,figsize=(13,8) if (pooled or delta) else (16,8),squeeze=False)
            fig.suptitle(f'{project} | {tp} months | Stage 4 baseline | '+('Both ITIs pooled' if pooled else '3s − 2s ITI' if delta else '2s vs 3s ITI')+' | last 4 sessions',fontsize=16,weight='bold')
            for r,(col,label,pct) in enumerate(chunk):
                for c,(sex,iti) in enumerate([('Female',None),('Male',None)] if (pooled or delta) else [('Female',2),('Female',3),('Male',2),('Male',3)]):
                    ax=axes[r,c]
                    base_ax(ax,sex,iti,('Δ ' if delta else '')+label)
                    if delta: ax.set_title(f'{sex} | Δ (3s − 2s ITI)',fontsize=10,fontweight='bold')
                    draw_group_bars(ax,q,project,sex,iti,col,pct,delta=(delta or pooled))
            fig.text(.5,.015,'Bars = group mean ± SEM; dots = individual animals. Ctrl = PBS/Sham; Trt = Lecanemab/Vaccine. Baseline stimulus duration: 2.0s.',ha='center',fontsize=9)
            fig.tight_layout(rect=[0,.04,1,.94]);pdf.savefig(fig);plt.close(fig)
    return True

def decile_pdf(path,deciles,project,tp):
    q=deciles[(deciles.Project==project)&(deciles.Timepoint_Months==tp)]
    if q.empty:return False
    with PdfPages(path) as pdf:
        for col,label,pct in METRICS:
            if col not in q:continue
            fig,axes=plt.subplots(1,4,figsize=(16,5.4))
            fig.suptitle(f'{project} | {tp} months | Stage 4 D1–D10 | {label}',fontsize=15,weight='bold')
            for ax,(sex,iti) in zip(axes,[('Female',2),('Female',3),('Male',2),('Male',3)]):
                base_ax(ax,sex,iti,label)
                v=q[(q.Sex==sex)&(q.Current_ITI_s==iti)]
                for geno,trt in GROUPS[project]:
                    x=v[(v.Genotype==geno)&(v.Treatment==trt)]
                    if x.empty:continue
                    means=x.groupby('Session_Progress_Decile')[col].mean().reindex(range(1,11))
                    z=means*100 if pct else means
                    ax.plot(range(1,11),z,color=COLORS[geno],ls=':' if trt in ('PBS','Sham') else '-',marker='o',ms=3,lw=1.4,label=f'{geno} {trt}')
                ax.set_xticks(range(1,11));ax.set_xlabel('Session decile');ax.legend(fontsize=6,loc='best')
            fig.tight_layout(rect=[0,0,1,.92]);pdf.savefig(fig);plt.close(fig)
    return True


def make_pooled_stage4(trial_csv):
    """Pool underlying valid 2s/3s trials BEFORE deriving performance rates and d-prime."""
    if not trial_csv.exists():
        return pd.DataFrame(),pd.DataFrame()
    import importlib.util
    extractor_path=Path(__file__).with_name('ATLAS_Dual_Phase_Extractor.py')
    if not extractor_path.exists():
        raise FileNotFoundError('Stage 4 pooled analysis requires ATLAS_Dual_Phase_Extractor.py alongside Graph Maker.')
    spec=importlib.util.spec_from_file_location('atlas_dual_extractor_metrics',extractor_path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    raw=read_csv(trial_csv)
    if raw.empty:return pd.DataFrame(),pd.DataFrame()
    raw=normalize(raw)
    raw=raw[raw['Baseline_Day_Number'].isin([1,2,3,4])].copy()
    if raw.empty:return pd.DataFrame(),pd.DataFrame()
    for col in ['Hit','Miss','False_Alarm','Correct_Rejection','Correct_Touch_Latency_IQR_Excluded','Incorrect_Touch_Latency_IQR_Excluded','Reward_Retrieval_Latency_IQR_Excluded']:
        if col not in raw:raw[col]=0
        raw[col]=pd.to_numeric(raw[col],errors='coerce').fillna(0)
    for col in ['Correct_Touch_Latency_Raw_s','Correct_Touch_Latency_IQRclean_s','Incorrect_Touch_Latency_Raw_s','Incorrect_Touch_Latency_IQRclean_s','Reward_Retrieval_Latency_Raw_s','Reward_Retrieval_Latency_IQRclean_s']:
        if col not in raw:raw[col]=np.nan
        raw[col]=pd.to_numeric(raw[col],errors='coerce')
    groupcols=['Project','Animal_ID','Sex','Genotype','Treatment','Timepoint_Months','SID','Baseline_Day_Number']
    if 'Database_Fingerprint' in raw:groupcols.append('Database_Fingerprint')
    session=[];deciles=[]
    for _,g in raw.groupby(groupcols,dropna=False,sort=False):
        rows=g.to_dict('records');meta={c:rows[0].get(c) for c in groupcols}
        session.append(mod.summarize_group(rows,meta))
        if 'Session_Progress_Decile' in g:
            for dec,d in g.groupby('Session_Progress_Decile'):
                if pd.isna(dec):continue
                deciles.append(mod.summarize_group(d.to_dict('records'),{**meta,'Session_Progress_Decile':int(float(dec))}))
    return pd.DataFrame(session),pd.DataFrame(deciles)

def pooled_decile_pdf(path,deciles,project,tp):
    q=deciles[(deciles.Project==project)&(deciles.Timepoint_Months==tp)]
    if q.empty:return False
    with PdfPages(path) as pdf:
        for col,label,pct in METRICS:
            if col not in q:continue
            fig,axes=plt.subplots(1,2,figsize=(14,6))
            fig.suptitle(f'{project} | {tp} months | Stage 4 baseline | ITIs pooled | D1-D10 | {label}',fontsize=15,weight='bold')
            for ax,sex in zip(axes,['Female','Male']):
                base_ax(ax,sex,None,label)
                v=q[q.Sex==sex]
                for geno,trt in GROUPS[project]:
                    x=v[(v.Genotype==geno)&(v.Treatment==trt)]
                    if x.empty:continue
                    means=x.groupby('Session_Progress_Decile')[col].mean().reindex(range(1,11))
                    z=means*100 if pct else means
                    ax.plot(range(1,11),z,color=COLORS[geno],ls=':' if trt in ('PBS','Sham') else '-',marker='o',ms=3,lw=1.4,label=f'{geno} {trt}')
                ax.set_xticks(range(1,11));ax.set_xlabel('Session decile');ax.legend(fontsize=7,loc='best')
            fig.tight_layout(rect=[0,0,1,.92]);pdf.savefig(fig);plt.close(fig)
    return True

def main():
    ap=argparse.ArgumentParser(description='Separate Stage 4 baseline and Probe 2b graph folders')
    ap.add_argument('input',nargs='?',help='Folder containing extractor CSV outputs')
    ap.add_argument('-o','--output-folder',help='Graph output directory')
    ap.add_argument('--preview',action='store_true')
    ap.add_argument('--project',choices=['Both','Lecanemab','Vaccine'],default='Both')
    ap.add_argument('--timepoint',choices=['All','6','9','12'],default='All')
    args=ap.parse_args()
    if not args.input or not args.output_folder:
        from tkinter import Tk,filedialog
        root=Tk();root.withdraw()
        if not args.input:args.input=filedialog.askdirectory(title='Select extractor output folder containing Stage4 and Probe2b CSVs')
        if not args.output_folder:args.output_folder=filedialog.askdirectory(title='Select destination for TWO graph folders')
        root.destroy()
    if not args.input or not args.output_folder:raise ValueError('Input and output folders are required.')
    src=Path(args.input);dest=Path(args.output_folder);dest.mkdir(parents=True,exist_ok=True)
    logs=[]
    pooled_stage4,pooled_stage4_deciles=make_pooled_stage4(src/'STAGE4_BASELINE_TRIAL_MASTER.csv')
    probe_failed=False
    probe=src/'CPT_67_COLUMN_ALL_DATABASES.csv'
    if probe.exists() and (src/'PROBE2B_TRIAL_MASTER.csv').exists():
        out=dest/'02_Probe2b_4_Sessions';out.mkdir(exist_ok=True)
        cmd=[sys.executable,str(Path(__file__).with_name('ATLAS_CPT_Graph_Maker_v1_8_ITI_panels_bardots.py')),str(probe),'-o',str(out),'--project',args.project,'--timepoint',args.timepoint]
        if args.preview:cmd.append('--preview')
        result=subprocess.run(cmd,check=False)
        logs.append(f'Probe 2b existing graph maker: exit code {result.returncode}')
        probe_failed = result.returncode != 0
    else:logs.append('Probe 2b SKIPPED: CPT_67_COLUMN_ALL_DATABASES.csv and/or PROBE2B_TRIAL_MASTER.csv missing')
    stage=src/'STAGE4_BASELINE_SESSION_METRICS_BY_ITI.csv'
    dec=src/'STAGE4_BASELINE_WITHIN_SESSION_DECILES_BY_ITI.csv'
    if stage.exists():
        ses=stage_session_filter(read_csv(stage)); animal=animal_means(ses)
        decile=stage_session_filter(read_csv(dec)) if dec.exists() else pd.DataFrame()
        decile_animal=animal_means(decile,['Session_Progress_Decile']) if not decile.empty else pd.DataFrame()
        out=dest/'01_Stage4_Last_4_Baseline_Sessions';out.mkdir(exist_ok=True)
        if not animal.empty:
            animal.to_csv(out/'STAGE4_GRAPH_ANIMAL_METRICS_BY_ITI.csv',index=False)
            projects=list(GROUPS) if args.project=='Both' else [args.project]
            months=[6,9,12] if args.timepoint=='All' else [int(args.timepoint)]
            if args.preview:projects=projects[:1];months=months[:1]
            for project in projects:
                pdest=out/project;pdest.mkdir(exist_ok=True)
                for tp in months:
                    for kind,is_delta in [('Whole_Session_2s_vs_3s',False),('ITI_Delta_3s_minus_2s',True)]:
                        p=pdest/f'{project}_{tp}_months_Stage4_{kind}.pdf'
                        if panel_pdf(p,animal,project,tp,is_delta):logs.append(str(p.relative_to(dest)))
                    if not decile_animal.empty:
                        p=pdest/f'{project}_{tp}_months_Stage4_Vigilance_D1-D10_2s_vs_3s.pdf'
                        if decile_pdf(p,decile_animal,project,tp):logs.append(str(p.relative_to(dest)))
                    if not pooled_stage4.empty:
                        pooled_animal=pooled_stage4.groupby(['Project','Animal_ID','Sex','Genotype','Treatment','Timepoint_Months'],as_index=False)[[m[0] for m in METRICS]].mean()
                        p=pdest/f'{project}_{tp}_months_Stage4_Whole_Session_ITIs_POOLED.pdf'
                        if panel_pdf(p,pooled_animal,project,tp,pooled=True):logs.append(str(p.relative_to(dest)))
                    if not pooled_stage4_deciles.empty:
                        pooled_decile_animal=pooled_stage4_deciles.groupby(['Project','Animal_ID','Sex','Genotype','Treatment','Timepoint_Months','Session_Progress_Decile'],as_index=False)[[m[0] for m in METRICS]].mean()
                        p=pdest/f'{project}_{tp}_months_Stage4_Vigilance_D1-D10_ITIs_POOLED.pdf'
                        if pooled_decile_pdf(p,pooled_decile_animal,project,tp):logs.append(str(p.relative_to(dest)))
            logs.append(f'Stage 4 source sessions: {ses.SID.nunique() if "SID" in ses else len(ses)} unique SID values overall')
        else:logs.append('Stage 4 SKIPPED: no eligible Stage 4 2s/3s data')
    else:logs.append('Stage 4 SKIPPED: STAGE4_BASELINE_SESSION_METRICS_BY_ITI.csv missing')
    (dest/'DUAL_PHASE_GRAPH_RUN_LOG.txt').write_text('\n'.join(logs)+'\n',encoding='utf-8')
    print('\n'.join(logs))
    print('Graph output:',dest)
    if probe_failed: raise RuntimeError('Probe 2b Graph Maker failed; Stage 4 may still have succeeded. Check Probe 2b error log.')
if __name__=='__main__':
    try:main()
    except Exception:traceback.print_exc();sys.exit(1)
