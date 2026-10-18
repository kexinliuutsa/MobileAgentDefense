"""Summarize already measured M4V native latency fields (NOT network/Android latency)."""
from __future__ import annotations
import argparse,csv,statistics
from collections import defaultdict

def pct(xs,p):
    if not xs:return None
    xs=sorted(xs);loc=(len(xs)-1)*p;lo=int(loc);hi=min(lo+1,len(xs)-1)
    return round(xs[lo]+(xs[hi]-xs[lo])*(loc-lo),3)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--csv',default='results/real_device_monitor/m4v_full_v3_replay/prefix_results.csv')
    a=p.parse_args()
    groups=defaultdict(list)
    with open(a.csv,newline='') as f:
        for r in csv.DictReader(f):
            region=r.get('evidence_region')
            if region=='HIGH':kind='HIGH_early_return'
            elif r.get('cf_checked')=='True':kind='CF_checked_'+str(region)
            else:kind='BASE_or_other_'+str(region)
            try: value=float(r['latency_total_ms'])
            except (ValueError,KeyError):continue
            groups[kind].append(value)
    print('M4V previously recorded model latency; no event ingestion/network/action gate timings')
    for kind,vals in sorted(groups.items()):
        print(kind,'n=',len(vals),'p50=',pct(vals,.5),'p95=',pct(vals,.95),
              'p99=',pct(vals,.99),'max=',round(max(vals),3))
if __name__=='__main__':main()
