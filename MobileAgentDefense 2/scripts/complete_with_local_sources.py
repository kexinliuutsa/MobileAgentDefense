#!/usr/bin/env python3
"""Copy actual local frozen / author code into this reviewed staging tree.

Usage: python3 scripts/complete_with_local_sources.py
Optional: --ours-root ... --author-root ... --paper-root ...
Does not train models, tune thresholds, alter original source files, or push to GitHub.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, sys, zipfile, datetime

ROOT=Path(__file__).resolve().parents[1]
HOME=Path.home()

OURS=(
 'evaluation/frozen_deployment_defense.py',
 'evaluation/frozen_v1v2v3_defense.py',
 'evaluation/frozen_v1v2v3_defense_hardened.py',
 'real_device_monitor/online_trajectory_defense_v3.py',
 'real_device_monitor/live_tail_monitor_v2.py',
 'real_device_monitor/history_timing_online_runner_v1.py',
)
AUTHOR=(
 'analysis/processing/judge_library.py',
 'analysis/processing/calculate_roc_auc_from_feature.py',
 'analysis/processing/extract_feature_of_swipes.py',
 'analysis/lib/motionevent_classes.py',
 'analysis/lib/feature_library.py',
 'analysis/lib/gesture_log_reader_utils.py',
 'humanized_swipe_classifiers.pkl',
 'raw_tap_classifier_us_across_clusters.pkl',
 'interval_classifier_microseconds_across_clusters.pkl',
)
MODEL_NAMES=(
 'session_head.joblib', 'strict_head.joblib', 'fusion_head.joblib',
 'human_reference_head.joblib','session_strict_head.joblib',
 'fake_artifact_calibration.json','feature_schema.json','split_manifest.json',
 'training_config.json',
)
BAD=re.compile(r'(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{18,}|github_pat_[A-Za-z0-9_]{18,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--ours-root',type=Path,default=HOME/'Desktop/GUI--Defense_Strategy')
 p.add_argument('--author-root',type=Path,default=HOME/'Desktop/Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark-main')
 p.add_argument('--paper-root',type=Path,default=HOME/'Desktop/GUI_AHB_PAPER_REBUILD')
 p.add_argument('--output-dir',type=Path,default=HOME/'Downloads')
 ns=p.parse_args()
 missing=[]; copied=[]; flagged=[]

 def cp(src,dst):
  if not src.is_file():missing.append(str(src.relative_to(ns.ours_root) if src.is_relative_to(ns.ours_root) else src.name));return
  if src.is_symlink(): flagged.append('symlink: '+str(src));return
  data=src.read_bytes()
  if src.suffix.lower() in {'.py','.md','.json','.sh','.yml','.yaml','.toml','.txt','.c','.h'}:
   text=data.decode('utf-8', errors='replace')
   if BAD.search(text): flagged.append('possible credential in '+str(dst.relative_to(ROOT)))
   if re.search(r'/Users/[A-Za-z0-9_.-]+/|/home/[A-Za-z0-9_.-]+/',text):flagged.append('hardcoded absolute user path in '+str(dst.relative_to(ROOT)))
  dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(data)
  copied.append((str(dst.relative_to(ROOT)),hashlib.sha256(data).hexdigest()))

 for f in OURS:cp(ns.ours_root/f,ROOT/'our_defense/frozen_online_v3'/f)
 for f in AUTHOR:cp(ns.author_root/f,ROOT/'author_defense'/f)
 # V3 frozen asset files are required rather than retraining/recalibrating them.
 art=ns.paper_root/'01_clean_code/offline_defenses/crossscaleguard_offline_v3/artifacts'
 for name in MODEL_NAMES:cp(art/name,ROOT/'our_defense/offline_v3_source/artifacts'/name)
 # Parser + adapter dependencies of the original frozen source.
 v2=ns.paper_root/'01_clean_code/offline_defenses/crossscaleguard_offline_v2'
 for fname in ('parser.py','adapter.py','features.py'):
  cp(v2/'src/crossscaleguard'/fname,ROOT/'our_defense/offline_v2_dependencies/src/crossscaleguard'/fname)

 # Stop on any unresolved critical source, even if earlier partial files were copied.
 if missing or flagged:
  print('FULL RELEASE NOT CREATED: review issues before publishing.')
  for m in missing: print('MISSING:',m)
  for f in flagged: print('REVIEW:',f)
  print('This does NOT modify your originals. You can provide --ours-root, --author-root, --paper-root.')
  return 2

 manifest={'release_kind':'merged-from-local-originals','n_copied':len(copied),
           'copied_files_sha256':dict(copied),
           'warning':'No model inference or full evaluation has been executed; license/security review required.'}
 (ROOT/'SOURCE_STATUS.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
 ns.output_dir.mkdir(parents=True,exist_ok=True)
 name='MobileAgentDefense_COMPLETE_NEEDS_REVIEW.zip'
 out=ns.output_dir/name
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for f in sorted(ROOT.rglob('*')):
   if f.is_file() and not any(x in f.parts for x in ('.git','__pycache__','.DS_Store','build','runs','results')):
    z.write(f, arcname='MobileAgentDefense/'+str(f.relative_to(ROOT)))
 print('CREATED:',out)
 print('Review licensing/privacy/source lineage before uploading; no test/evaluation claimed.')
 return 0
if __name__=='__main__':raise SystemExit(main())
