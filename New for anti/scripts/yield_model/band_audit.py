"""How often did actual yields land inside the published bands?

Usage: python3 band_audit.py     # from scripts/yield_model; writes band_audit.json

For every region with a model and a training table, each season is forecast
from earlier seasons only with the region's published trend form, and sigma
is the RMSE of the ten forecasts before it -- the way the cards build their
68% band (point +/- sigma). The share of seasons inside +/- sigma and
+/- Z95 * sigma is then counted.

2026-11-27, 1,260 seasons in 63 regions: 65.8% inside the 68% band (fine),
but only 90.3% inside a 1.96-sigma "95%" band -- yield misses have fat tails
(the 95th percentile miss is 2.54 sigma). The 95% bands in every country's
predict.py now use Z95 = 2.5.
"""
import os,json,glob,numpy as np,pandas as pd
def trend(y,Y,deg,win):
    if win:
        m=y>=y.max()-win+1
        if m.sum()>=max(deg+2,8): y,Y=y[m],Y[m]
    return np.poly1d(np.polyfit(y,np.log(Y),deg))
rows=[]
for mj in sorted(glob.glob('*/models/*.json')):
    c=mj.split('/')[0]; k=os.path.basename(mj)[:-5]
    tp=f'{c}/training/{k}.csv'
    if not os.path.exists(tp): continue
    try: t=json.load(open(mj)).get('trend') or {}
    except Exception: continue
    deg,win=t.get('degree') or 1,t.get('window')
    df=pd.read_csv(tp); yc=next((x for x in df.columns if x.startswith('yield')),None)
    if not yc or 'year' not in df: continue
    df=df[['year',yc]].dropna(); df=df[df[yc]>0]
    y=df.year.values.astype(float); Y=df[yc].values.astype(float)
    preds={}
    for i,tt in enumerate(y):
        tr=y<tt
        if tr.sum()<12: continue
        preds[tt]=(Y[i], float(np.exp(trend(y[tr],Y[tr],deg,win)(tt))))
    yrs=sorted(preds)
    for j,tt in enumerate(yrs):
        prior=yrs[max(0,j-10):j]
        if len(prior)<8: continue
        sig=np.sqrt(np.mean([(preds[p][0]-preds[p][1])**2 for p in prior]))
        a,p=preds[tt]; z=abs(a-p)/sig
        rows.append((c,k,int(tt),z))
d=pd.DataFrame(rows,columns=['country','key','year','z'])
Z95=2.5
print('seasons',len(d),'regions',d.key.nunique())
print('in 68% band',round((d.z<=1).mean()*100,1),'% | in 95% band',round((d.z<=1.96).mean()*100,1),'%')
rec=d[d.year>=2016]; print('since 2016:',round((rec.z<=1).mean()*100,1),round((rec.z<=1.96).mean()*100,1), len(rec))
print('k for 68%:',round(d.z.quantile(.68),2),' k for 95%:',round(d.z.quantile(.95),2))
g=d.groupby('country').z.agg(n='size',in68=lambda s:round((s<=1).mean()*100),in95=lambda s:round((s<=1.96).mean()*100),q68=lambda s:round(s.quantile(.68),2),q95=lambda s:round(s.quantile(.95),2))
print(g.sort_values('in68').to_string())
print('in 2.5-sigma band',round((d.z<=Z95).mean()*100,1),'%')
json.dump({"seasons":int(len(d)),"regions":int(d.key.nunique()),
           "in_68_band_pct":round(float((d.z<=1).mean()*100),1),
           "in_196_band_pct":round(float((d.z<=1.96).mean()*100),1),
           "in_z95_band_pct":round(float((d.z<=Z95).mean()*100),1),"z95":Z95,
           "z_quantile_68":round(float(d.z.quantile(.68)),2),"z_quantile_95":round(float(d.z.quantile(.95)),2),
           "by_country":json.loads(g.to_json(orient="index"))},
          open("band_audit.json","w"),indent=1)
