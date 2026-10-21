#!/usr/bin/env python3
"""Mobile-Agent-E (official) -> validated Type-B uinput -> kernel getevent ->
frozen Python CrossScaleGuard V3, EAD from g5 (non-blocking SHADOW scoring).

No defense retraining, no surrogate scores, no ADB `input tap/swipe` fallback.
Requires the user's already-validated RUN_AUTOGLM_V3_TYPEB_SHADOW_QQMUSIC.py
as the shared independent monitor, plus the official Mobile-Agent-E source.

No action is sent in --preflight-only. In real mode use a non-sensitive phone
and a harmless, clearly specified task; Mobile-Agent-E sends screenshots to
its selected inference/captioning services. The original Mobile-Agent-E may
save screenshots in its own experiment directory.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

ROOT_REL = Path('01_clean_code/offline_defenses/crossscaleguard_offline_v3/run.py')
ORIGINAL_ADAPTER = Path.home()/'Downloads'/'RUN_AUTOGLM_V3_TYPEB_SHADOW_QQMUSIC.py'
TYPEB_REMOTE = '/data/local/tmp/uinput_typeb_agent_compat'


def say(*args):
    print(*args, flush=True)


def check_official_source(repo: Path):
    """Static structural audit, deliberately never imports large model deps."""
    for rel in ['run.py','inference_agent_E.py',
                'MobileAgentE/agents.py','MobileAgentE/controller.py']:
        fp=repo/rel
        if not fp.is_file():
            raise FileNotFoundError(f'Mobile-Agent-E official source missing: {fp}')
        ast.parse(fp.read_text(encoding='utf-8'), filename=str(fp))
    agents=(repo/'MobileAgentE/agents.py').read_text(encoding='utf-8')
    controller=(repo/'MobileAgentE/controller.py').read_text(encoding='utf-8')
    inference=(repo/'inference_agent_E.py').read_text(encoding='utf-8')
    requirements={
        'Operator.execute_atomic_action':r'def\s+execute_atomic_action\s*\(',
        'Operator calls tap':r'\btap\(adb_path\s*,',
        'Operator calls swipe':r'\bswipe\(adb_path\s*,',
    }
    for name,pattern in requirements.items():
        if not re.search(pattern,agents):
            raise RuntimeError(f'Official Mobile-Agent-E interface changed: {name}. Refuse silent fallback.')
    if not all(re.search(r'def\s+'+n+r'\s*\(',controller) for n in ('tap','swipe')):
        raise RuntimeError('Official controller no longer exports tap/swipe.')
    if not re.search(r'def\s+run_single_task\s*\(',inference):
        raise RuntimeError('Official inference_agent_E.run_single_task missing.')
    return 'OFFICIAL INTERFACE PASS (Operator -> controller.tap/swipe)'


def locate_mobile_e(value):
    candidates=[]
    if value:
        candidates.append(Path(value).expanduser())
    if os.getenv('MOBILE_AGENT_E_HOME'):
        candidates.append(Path(os.environ['MOBILE_AGENT_E_HOME']).expanduser())
    home=Path.home()
    candidates += [
        home/'Desktop/MobileAgent/Mobile-Agent-E',
        home/'Downloads/MobileAgent/Mobile-Agent-E',
        home/'Desktop/GUI_AHB_PAPER_REBUILD/external/MobileAgent/Mobile-Agent-E',
        home/'Desktop/Mobile-Agent-E',
        home/'Downloads/Mobile-Agent-E',
    ]
    for p in candidates:
        if (p/'MobileAgentE/agents.py').is_file():
            return p.resolve()
    raise FileNotFoundError(
        'Mobile-Agent-E official repository not found. Clone official X-PLUG/MobileAgent '
        'then provide --mobile-agent-e /path/to/MobileAgent/Mobile-Agent-E. '
        'No project or model files were changed.')


def load_existing_adapter(filename: Path):
    if not filename.is_file():
        raise FileNotFoundError(f'Existing validated AutoGLM Type-B Runner missing: {filename}')
    spec=importlib.util.spec_from_file_location('csg_prevalidated_typeb_shadow',filename)
    if not spec or not spec.loader:
        raise RuntimeError('Failed to load shared validated Shadow code')
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    needed=('adb_devices','verify_typeb_preflight','load_v3','Shadow','jsonline')
    if not all(hasattr(module,n) for n in needed):
        raise RuntimeError(f'Existing Type-B Runner interface changed; expected {needed}')
    return module


def require_api_environment():
    backbone=os.getenv('BACKBONE_TYPE','OpenAI')
    key_name={'OpenAI':'OPENAI_API_KEY','Gemini':'GEMINI_API_KEY','Claude':'CLAUDE_API_KEY'}.get(backbone)
    if not key_name:
        raise RuntimeError('Mobile-Agent-E BACKBONE_TYPE must be OpenAI, Gemini, or Claude')
    missing=[name for name in (key_name,'QWEN_API_KEY') if not os.getenv(name)]
    if missing:
        raise RuntimeError('Official Mobile-Agent-E backend missing environment vars: '
                           + ', '.join(missing)
                           + '. Do not paste credentials into scripts or chat.')
    return backbone


def parse_args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,default=Path.cwd(),help='GUI_AHB_PAPER_REBUILD root')
    p.add_argument('--mobile-agent-e',type=Path,help='Official Mobile-Agent-E source directory')
    p.add_argument('--existing-typeb-runner',type=Path,default=ORIGINAL_ADAPTER,
                   help='Original validated AutoGLM Type-B Shadow Runner, reused read-only')
    p.add_argument('--expected-package',default=None,help='Package that must be foreground at preflight')
    p.add_argument('--task',default=None,help='One approved, non-sensitive task')
    p.add_argument('--max-steps',type=int,default=12)
    p.add_argument('--tap-ms',type=int,default=100)
    p.add_argument('--swipe-ms',type=int,default=450)
    p.add_argument('--preflight-only',action='store_true',help='No taps, model imports, or API calls')
    return p.parse_args()


def main():
    a=parse_args()
    project=a.project.expanduser().resolve()
    if not a.preflight_only and not a.task:
        raise ValueError('Provide --task, or use --preflight-only')
    if not 1 <= a.max_steps <= 100:
        raise ValueError('--max-steps must be 1..100')
    if not 50 <= a.tap_ms <= 500 or not 150 <= a.swipe_ms <= 2000:
        raise ValueError('Tap must be 50..500ms and Swipe 150..2000ms')
    if not shutil.which('adb'):
        raise RuntimeError('adb not found')
    if not (project/ROOT_REL).is_file():
        raise FileNotFoundError('Frozen CrossScaleGuard V3 missing at '+str(project/ROOT_REL))

    repo=locate_mobile_e(a.mobile_agent_e)
    say(check_official_source(repo))
    say('Mobile-Agent-E source:',repo)
    original=load_existing_adapter(a.existing_typeb_runner.expanduser().resolve())
    adb=original.adb_devices()
    provenance=original.verify_typeb_preflight(
        project,adb,TYPEB_REMOTE,expected_package=a.expected_package,verify_hash=True)
    if a.preflight_only:
        say('\nMOBILE-AGENT-E TYPE-B PREFLIGHT PASS')
        say('No inference, no touch injection, no model changes.')
        say('Next: check official Mobile-Agent-E Python dependencies/API environment before a safe task.')
        return 0
    backbone=require_api_environment()
    say('\nMOBILE-AGENT-E TYPE-B SHADOW (REAL DEVICE)')
    say('Task:',a.task)
    say('Backend:',backbone,'(official Mobile-Agent-E; separate Qwen caption API required)')
    say('Type-B: verified 1080x2400 executor. EAD from completed g5, Frozen Full Fusion only.')
    say('Other actions (Type/Back/Home/Enter/Wait) are logged as non-touch.')
    say('Screenshots are sent to official model services and may be stored in experiment output.')
    say('NO payments, account changes, posting, messages, deletes or sensitive screens.')
    if input('Type YES to authorize this single task on the PHONE: ').strip()!='YES':
        say('CANCELLED. No actions sent.')
        return 0

    outdir=(project/'real_device_online'/'mobile_agent_e_typeb_shadow'
            /dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    outdir.mkdir(parents=True,exist_ok=False)
    # Use ORIGINAL frozen model and ORIGINAL validated watcher's parser.
    v3,params=original.load_v3(project)
    watcher=original.Shadow(project,adb,TYPEB_REMOTE,
                            outdir/'getevent_all_devices.log',outdir,v3,params,
                            a.tap_ms,a.swipe_ms)
    logfile=outdir/'agent_actions.jsonl'
    touch_count=[0]
    actions=[]
    stop_reason='not_started'
    failure=None
    agent_returned=False
    original_cwd=Path.cwd()
    before_modules={}
    original_tap=None
    original_swipe=None

    def perform_touch(kind, coords):
        if kind=='Tap':
            if len(coords)!=2:
                raise ValueError('Tap requires 2 coordinates')
        elif kind=='Swipe':
            if len(coords)!=4:
                raise ValueError('Swipe requires 4 coordinates')
        else:
            raise AssertionError(kind)
        coords=[int(v) for v in coords]
        if any(not 0<=v<limit for v,limit in zip(coords,([1080,2400] if kind=='Tap' else [1080,2400,1080,2400]))):
            raise ValueError(f'Invalid 1080x2400 {kind} coordinates: {coords}')
        record={'seq':len(actions)+1,'kind':kind,'coords':coords,
                'time':dt.datetime.now().isoformat(timespec='seconds'),
                'hardware_g_before':watcher.last_n}
        actions.append(record)
        original.jsonline(logfile,record|{'phase':'started'})
        if kind=='Tap':
            watcher.do('tap',*coords,a.tap_ms,0)
        else:
            watcher.do('swipe',*coords,a.swipe_ms,0,'linear',0)
        # NEVER silently score a planned action instead of observed kernel events.
        result=watcher.score_new(1,kind)
        touch_count[0]+=1
        record['hardware_g_after']=watcher.last_n
        record['score']=result[-1].get('score') if result else None
        original.jsonline(logfile,record|{'phase':'completed'})

    def tap_typeb(adb_path,x,y):
        perform_touch('Tap',(x,y))

    def swipe_typeb(adb_path,x1,y1,x2,y2):
        perform_touch('Swipe',(x1,y1,x2,y2))

    try:
        watcher.start()
        # Official agent imports are intentionally deferred until after preflight.
        sys.path.insert(0,str(repo))
        os.chdir(repo)
        from MobileAgentE import controller, agents
        # Assertions prevent silent unexpected fallback to adb input tap/swipe.
        source=inspect.getsource(agents.Operator.execute_atomic_action)
        if 'tap(adb_path,' not in source or 'swipe(adb_path,' not in source:
            raise RuntimeError('Mobile-Agent-E action interface changed; aborting to preserve Type-B provenance')
        original_tap,original_swipe=agents.tap,agents.swipe
        before_modules={'controller_tap':controller.tap,'controller_swipe':controller.swipe}
        agents.tap=tap_typeb
        agents.swipe=swipe_typeb
        controller.tap=tap_typeb
        controller.swipe=swipe_typeb
        from inference_agent_E import run_single_task, DEFAULT_PERCEPTION_ARGS
        say('\nAGENT START: original Mobile-Agent-E planner/perception, TYPE-B touch only.')
        stop_reason='running'
        # Keep official single-task semantics; disable cross-task evolution by default.
        run_single_task(
            instruction=a.task,
            run_name='single',
            log_root=str(outdir/'official_mobile_agent_e'),
            task_id='run',
            perceptor=None,
            perception_args=DEFAULT_PERCEPTION_ARGS,
            max_itr=a.max_steps,
            max_consecutive_failures=4,
            max_repetitive_actions=4,
            overwrite_log_dir=False,
            enable_experience_retriever=False,
            temperature=0.0,
            screenrecord=False,
        )
        agent_returned=True
        stop_reason='agent_returned_check_official_log'
    except KeyboardInterrupt:
        stop_reason='user_interrupt'
        failure='KeyboardInterrupt'
        say('Interrupted by user; stopping kernel capture.')
    except Exception as e:
        failure=f'{type(e).__name__}: {e}'
        stop_reason='agent_or_alignment_error'
        say('RUN STOPPED:',failure)
        traceback.print_exc()
    finally:
        # Restore official names and current directory even after exception.
        try:
            if original_tap is not None:
                agents.tap=original_tap
                agents.swipe=original_swipe
            if before_modules:
                controller.tap=before_modules['controller_tap']
                controller.swipe=before_modules['controller_swipe']
        except Exception:
            pass
        os.chdir(original_cwd)
        watcher.stop()

    try:
        final=watcher.final()
    except Exception as e:
        final={'error':f'{type(e).__name__}: {e}'}
        say('FINAL V3 AUDIT FAILED:',final['error'])

    success='unknown'
    if agent_returned:
        answer=input('Did task REALLY succeed? [y/n/u]: ').strip().lower()
        success={'y':'yes','n':'no'}.get(answer,'unknown')
    events=[]
    if watcher.eventsfile.exists():
        events=[json.loads(s) for s in watcher.eventsfile.read_text().splitlines() if s.strip()]
    first_alarm=next((e['hardware_g'] for e in events if e.get('detected') is True),None)
    summary={
        'agent':'Mobile-Agent-E',
        'agent_source':'official X-PLUG/MobileAgent/Mobile-Agent-E, unchanged',
        'task':a.task,'backbone':backbone,'task_success_manual':success,
        'stopping_reason':stop_reason,'error':failure,
        'typeb_wrapped_actions':touch_count[0],
        'detector':'original frozen CrossScaleGuard V3 Full Fusion, EAD k=5',
        'provenance':'observed kernel Type-B Virtual Touch Screen, not planned actions',
        'preflight':provenance,
        'v3_final':final,'first_alarm_g':first_alarm,
        'anytime_alarm_after_g5':first_alarm is not None,
        'prefixes_scored':sum(e.get('v3_status')=='ok' for e in events),
        'official_log_dir':str(outdir/'official_mobile_agent_e'/'single'/'run'),
        'original_defense_modified':False,'api_key_saved':False,
    }
    (outdir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    say('\nFINAL MOBILE-AGENT-E TYPE-B SUMMARY:',json.dumps(summary,ensure_ascii=False,indent=2,default=str))
    say('SAVED:',outdir)
    return 0 if not failure and final.get('alignment_pass') is True else 2


if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)