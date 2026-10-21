#!/usr/bin/env python3
"""Official MAI-UI-8B Navigation Agent -> existing Type-B -> original Frozen V3.

Designed for the user's validated 1080x2400 Android phone and QQ Music.
Official MAI-UI planner is imported unmodified from MAI-UI/src/mai_naivigation_agent.py.
Screenshot-only observation: NO UiAutomator, XML, custom planner, or reflection.

First milestones:
  --self-test: no device, no API, no touch
  --preflight-only: read-only ADB, hash, source & package checks
  --model-probe-only: one REAL model prediction, screenshot sent; NO touch
  --pilot-one-tap: one REAL model prediction; execute ONLY if 'click'
Normal run is opt-in and requires explicit YES authorization.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

SCREEN=(1080, 2400)
APP_PACKAGE='com.tencent.qqmusic'
ORIGINAL_ADAPTER=Path.home()/'Downloads'/'RUN_AUTOGLM_V3_TYPEB_SHADOW_QQMUSIC.py'



def _attach_live_p74_to_original_v3_shadow(shadow, project, outdir):
    """Only instrumentation on validated native Shadow; never changes GUI actions."""
    if os.environ.get("CSG_DUAL_ONLINE") != "1":
        return shadow
    shared=Path(__file__).resolve().parents[1]
    if str(shared) not in sys.path:
        sys.path.insert(0,str(shared))
    from live_dual_shadow import wrap
    return wrap(shadow,project,outdir)


def jdump(path:Path, obj:Any):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')


def jappend(path:Path,obj:Any):
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(obj,ensure_ascii=False,default=str)+'\n')


def adb_cmd(adb:list[str],*argv:str,timeout:int=20)->str:
    p=subprocess.run(adb+list(argv),capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError('ADB command failed: '+repr(list(argv))+'; stderr='+p.stderr.decode('utf-8','replace')[-500:])
    return p.stdout.decode('utf-8','replace').strip()


def screenshot(adb:list[str])->bytes:
    p=subprocess.run(adb+['exec-out','screencap','-p'],capture_output=True,timeout=25)
    if p.returncode or not p.stdout.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Unable to capture real Android PNG screenshot: '+p.stderr.decode('utf-8','replace')[-250:])
    return p.stdout


def normalized_pixel(pt,screen=SCREEN)->tuple[int,int]:
    """Official MAI parser divides model coordinates by 999; input here is [0,1]."""
    if not isinstance(pt,(list,tuple)) or len(pt)!=2:
        raise ValueError(f'Expected normalized [x,y], got {pt!r}')
    x,y=pt
    if any(isinstance(z,bool) or not isinstance(z,(int,float)) or not math.isfinite(z) or not (0<=z<=1) for z in (x,y)):
        raise ValueError(f'MAI-UI coordinate outside [0,1] or nonnumeric: {pt!r}')
    return (min(screen[0]-1,round(x*(screen[0]-1))),min(screen[1]-1,round(y*(screen[1]-1))))


def swipe_target(start,direction,screen=SCREEN):
    if direction not in ('up','down','left','right'):
        raise ValueError('Unsupported swipe direction '+repr(direction))
    horizontal=direction in ('left','right')
    amount=round((screen[0] if horizontal else screen[1])*(.22 if horizontal else .23))
    dx={'left':-amount,'right':amount}.get(direction,0)
    dy={'up':-amount,'down':amount}.get(direction,0)
    # Keep endpoints clear of system bars (and the top status bar).
    lo_x,hi_x=28,screen[0]-29
    lo_y,hi_y=72,screen[1]-135
    x,y=start
    if dx>0: x=min(x,hi_x-dx)
    if dx<0: x=max(x,lo_x-dx)
    if dy>0: y=min(y,hi_y-dy)
    if dy<0: y=max(y,lo_y-dy)
    x=max(lo_x,min(hi_x,x));y=max(lo_y,min(hi_y,y))
    end_x=x+dx;end_y=y+dy
    if not (lo_x<=end_x<=hi_x and lo_y<=end_y<=hi_y):
        raise ValueError('Cannot place swipe within Android touch area')
    return (x,y),(end_x,end_y)


def map_action(action:dict, pilot_one_tap=False)->dict:
    """Deterministic adapter mapping; no re-planning and no action substitution."""
    if not isinstance(action,dict) or not isinstance(action.get('action'),str):
        raise ValueError('Official MAI returned no valid structured action: '+repr(action))
    kind=action['action'].strip().lower()
    if pilot_one_tap and kind!='click':
        raise ValueError(f'PILOT ONE-TAP: MAI chose {kind!r}, not click; no gesture permitted')
    if kind=='click':
        return {'kind':'typeb_tap','start':normalized_pixel(action.get('coordinate'))}
    if kind=='drag':
        a=normalized_pixel(action.get('start_coordinate'))
        b=normalized_pixel(action.get('end_coordinate'))
        if a==b:raise ValueError('MAI drag has same start/end')
        return {'kind':'typeb_swipe','start':a,'end':b,'semantic':'drag'}
    if kind=='swipe':
        pos=normalized_pixel(action['coordinate']) if 'coordinate' in action else (SCREEN[0]//2,SCREEN[1]//2)
        a,b=swipe_target(pos,action.get('direction'))
        return {'kind':'typeb_swipe','start':a,'end':b,'semantic':'swipe'}
    if kind=='type':
        value=action.get('text')
        if not isinstance(value,str) or not value or len(value)>100:
            raise ValueError('Invalid input string')
        return {'kind':'adbkeyboard_text','text':value}
    if kind=='system_button':
        button=action.get('button','')
        if button not in ('back','enter'):
            raise ValueError(f'Unsupported system_button {button!r}: remain in QQ Music')
        return {'kind':'adb_key','button':button}
    if kind=='wait':return {'kind':'wait'}
    if kind=='terminate':
        status=action.get('status','')
        if status not in ('success','fail'):raise ValueError('Invalid termination status')
        return {'kind':'terminate','status':status}
    if kind=='answer':return {'kind':'answer','text':str(action.get('text',''))[:500]}
    if kind=='open':
        return {'kind':'open_requested','text':str(action.get('text',''))}
    if kind=='long_press':
        # Validated Type-B tap dwell is limited to 500ms; do NOT silently replace with ADB.
        raise ValueError('Unsupported long_press: validated Type-B binary cannot produce verified >500ms hold')
    raise ValueError(f'Unsupported official MAI action: {kind!r}')


def resolve_src(repo:Path)->Path:
    candidates=[repo/'MAI-UI'/'src',repo/'src',repo]
    for d in candidates:
        if all((d/f).is_file() for f in ('mai_naivigation_agent.py','base.py','prompt.py','unified_memory.py','utils.py')):
            return d
    raise FileNotFoundError('Official MAI-UI Navigation sources missing. Expected MAI-UI/MAI-UI/src/mai_naivigation_agent.py under '+str(repo))


def load_existing(path:Path):
    if not path.is_file():raise FileNotFoundError('Original existing AutoGLM/Type-B/Frozen V3 module missing: '+str(path))
    spec=importlib.util.spec_from_file_location('user_original_typeb_v3_shadow',path)
    if spec is None or spec.loader is None:raise RuntimeError('Cannot import validated original runner')
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod


def load_official(src:Path):
    sys.path.insert(0,str(src))
    from mai_naivigation_agent import MAIUINaivigationAgent, parse_action_to_structure_output
    return MAIUINaivigationAgent,parse_action_to_structure_output


def input_chinese(adb:list[str],text:str):
    ime=adb_cmd(adb,'shell','settings','get','secure','default_input_method')
    if 'adbkeyboard' not in ime.lower():
        raise RuntimeError('MAI requested TYPE but ADBKeyboard is not the active IME. Refusing to replace Chinese text with Latin; active IME='+ime)
    b64=base64.b64encode(text.encode('utf-8')).decode('ascii')
    adb_cmd(adb,'shell','am','broadcast','-a','ADB_INPUT_B64','--es','msg',b64)
    return {'input_backend':'ADBKeyboard/ADB_INPUT_B64','bytes_utf8':len(text.encode('utf-8'))}


def execute_plan(plan,shadow,adb,model_action,args):
    """Returns (typeb_count, description); non-TypeB operations reported separately."""
    k=plan['kind']
    if k=='typeb_tap':
        x,y=plan['start']
        shadow.do('tap',x,y,args.dwell_ms,'0')
        shadow.score_new(1,'Tap')
        return 1,'Type-B tap'
    if k=='typeb_swipe':
        x,y=plan['start'];a,b=plan['end']
        shadow.do('swipe',x,y,a,b,args.swipe_ms,'0','linear','0')
        shadow.score_new(1,'Swipe')
        return 1,'Type-B swipe'
    if k=='adbkeyboard_text':
        if not args.allow_text:raise RuntimeError('TYPE requested but --allow-text is OFF; no action executed')
        input_chinese(adb,plan['text'])
        return 0,'Non-TypeB ADBKeyboard text'
    if k=='adb_key':
        if not args.allow_adb_key:raise RuntimeError('System BACK/ENTER requested but --allow-adb-key is OFF')
        adb_cmd(adb,'shell','input','keyevent',{'back':'KEYCODE_BACK','enter':'KEYCODE_ENTER'}[plan['button']])
        return 0,'Non-TypeB ADB keyevent '+plan['button']
    if k=='wait':
        time.sleep(2)
        return 0,'Wait (no gesture)'
    if k=='open_requested':
        if plan['text'].lower().replace(' ','') not in ('qqmusic','qq音乐','com.tencent.qqmusic'):
            raise RuntimeError('Model requested a different app; blocked: '+plan['text'])
        # The initial preflight already verified QQ Music foreground. Do not re-launch.
        return 0,'App already foreground; open treated as no-op'
    if k in ('terminate','answer'):
        return 0,k+' (model statement, no gesture)'
    raise RuntimeError('Unexpected plan kind: '+k)


def preflight(args,original,src):
    if not shutil.which('adb'):raise RuntimeError('adb not in PATH')
    adb=original.adb_devices()
    meta=original.verify_typeb_preflight(args.project,adb,args.remote_binary,args.expected_package,True)
    meta['official_mai_src']=str(src)
    meta['official_mai_navigation_sha256']=hashlib.sha256((src/'mai_naivigation_agent.py').read_bytes()).hexdigest()
    return adb,meta


def self_test():
    assert normalized_pixel([0,0])==(0,0)
    assert normalized_pixel([1,1])==(1079,2399)
    assert normalized_pixel([.5,.5])==(540,1200)
    assert map_action({'action':'click','coordinate':[.5,.5]},True)=={'kind':'typeb_tap','start':(540,1200)}
    assert map_action({'action':'drag','start_coordinate':[.1,.1],'end_coordinate':[.8,.8]})['kind']=='typeb_swipe'
    assert map_action({'action':'swipe','direction':'up'})['kind']=='typeb_swipe'
    assert map_action({'action':'terminate','status':'success'})['kind']=='terminate'
    for bad in ([1.1,.2],[-1,.4],['x',.3],[float('nan'),.2]):
        try:normalized_pixel(bad)
        except ValueError:pass
        else:raise AssertionError('Bad normalized coordinate accepted')
    for bad in [{'action':'long_press','coordinate':[.1,.2]}, {'action':'click','coordinate':[1.1,.2]}]:
        try:map_action(bad)
        except ValueError:pass
        else:raise AssertionError('Unsupported/invalid action accepted')
    records=[]
    class DryShadow:
        def do(self,*z):records.append(('do',z))
        def score_new(self,*z):records.append(('score',z))
    class Args:dwell_ms=100;swipe_ms=450;allow_text=False;allow_adb_key=False
    assert execute_plan(map_action({'action':'click','coordinate':[.25,.3]}),DryShadow(),None,None,Args())[0]==1
    assert records[0][1][0]=='tap' and records[1][1]==(1,'Tap')
    records.clear()
    assert execute_plan(map_action({'action':'drag','start_coordinate':[.2,.3],'end_coordinate':[.8,.7]}),DryShadow(),None,None,Args())[0]==1
    assert records[0][1][0]=='swipe' and records[1][1]==(1,'Swipe')
    print('MAI-UI-8B -> ORIGINAL Type-B/Frozen-V3 ADAPTER SELF-TEST PASS (offline; no phone, no API)')



def official_smoke_test(repo:Path):
    """No ADB/network: import EXACT local official code and test its own parser."""
    src=resolve_src(repo.expanduser().resolve())
    Agent,parse_action=load_official(src)
    sample='<thinking>Click search</thinking><tool_call>{"name":"mobile_use","arguments":{"action":"click","coordinate":[499,499]}}</tool_call>'
    z=parse_action(sample)
    assert z['action_json']['action']=='click'
    assert abs(z['action_json']['coordinate'][0]-499/999)<1e-7
    assert map_action(z['action_json'])['kind']=='typeb_tap'
    agent=Agent(llm_base_url='http://127.0.0.1:8000/v1',model_name='MAI-UI-8B')
    assert 'mobile_use' in agent.system_prompt
    print('OFFICIAL MAI-UI NAVIGATION PARSER / PROMPT SMOKE-TEST PASS (offline)')
    print('Source:',src/'mai_naivigation_agent.py')


def cli():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--project',type=Path,default=Path.home()/'Desktop'/'GUI_AHB_PAPER_REBUILD')
    p.add_argument('--mai-repo',type=Path,default=Path.home()/'Desktop'/'MAI-UI')
    p.add_argument('--original-adapter',type=Path,default=ORIGINAL_ADAPTER)
    p.add_argument('--expected-package',default=APP_PACKAGE)
    p.add_argument('--remote-binary',default='/data/local/tmp/uinput_typeb_agent_compat')
    p.add_argument('--api-base',default='http://127.0.0.1:8000/v1',help='SSH-tunneled vLLM OpenAI-compatible base URL')
    p.add_argument('--model',default='MAI-UI-8B')
    p.add_argument('--task',default='')
    p.add_argument('--max-steps',type=int,default=10)
    p.add_argument('--max-actions',type=int,default=10)
    p.add_argument('--max-tokens',type=int,default=2048)
    p.add_argument('--api-timeout',type=float,default=120)
    p.add_argument('--request-interval',type=float,default=2)
    p.add_argument('--dwell-ms',type=int,default=100)
    p.add_argument('--swipe-ms',type=int,default=450)
    p.add_argument('--allow-text',action='store_true',help='Allow input via existing ADBKeyboard (not a Type-B gesture)')
    p.add_argument('--allow-adb-key',action='store_true',help='Allow BACK and ENTER via ADB keyevent (not Type-B)')
    p.add_argument('--preflight-only',action='store_true',help='Read-only ADB and sources; NO API, NO touch')
    p.add_argument('--model-probe-only',action='store_true',help='One official MAI inference on real screenshot, NO touch')
    p.add_argument('--pilot-one-tap',action='store_true',help='Only execute if first MAI action is click; stop after 1 Type-B tap')
    p.add_argument('--self-test',action='store_true',help='Offline unit checks; no ADB and no API')
    p.add_argument('--official-smoke-test',action='store_true',help='Use the actual local MAI-UI agent/parser offline (requires Mac navigation dependencies)')
    a=p.parse_args()
    if a.self_test:self_test();return 0
    if a.official_smoke_test:official_smoke_test(a.mai_repo);return 0
    if not 1<=a.max_steps<=100 or not 1<=a.max_actions<=100: p.error('--max-steps/--max-actions must be 1..100')
    if not 50<=a.dwell_ms<=500 or not 150<=a.swipe_ms<=2000:p.error('Type-B durations outside validated binary limits')
    if a.max_tokens<256:p.error('max-tokens too small for official MAI XML+JSON output')
    if not 0<=a.request_interval<=30:p.error('request-interval must be 0..30')
    if a.pilot_one_tap and a.model_probe_only:p.error('Choose one of --pilot-one-tap/--model-probe-only')
    if not a.preflight_only and not a.task:p.error('--task required for inference or execution')
    a.project=a.project.expanduser().resolve()
    src=resolve_src(a.mai_repo.expanduser().resolve())
    original=load_existing(a.original_adapter.expanduser().resolve())
    adb,preflight_info=preflight(a,original,src)
    if a.preflight_only:
        print('MAI-UI PREFLIGHT PASS: original Type-B checked, frozen model files present, 1080x2400, QQ Music foreground, official MAI code found. NO API/TOUCH.')
        return 0
    # Import original code after preflight; predictions use official navigation class and prompts unmodified.
    Agent,_=load_official(src)
    from PIL import Image
    from openai import OpenAI
    agent=Agent(llm_base_url=a.api_base,model_name=a.model,
                runtime_conf={'history_n':3,'temperature':0.0,'top_k':-1,'top_p':1.0,'max_tokens':a.max_tokens})
    agent.llm=OpenAI(base_url=a.api_base,api_key='empty',timeout=a.api_timeout)
    outdir=a.project/'real_device_online'/'mai_ui_8b_typeb_shadow'/dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    outdir.mkdir(parents=True,exist_ok=False)
    jdump(outdir/'run_config.json',{'agent':'Official MAIUINaivigationAgent','model':a.model,'task':a.task,
           'src':str(src),'source_sha256':preflight_info['official_mai_navigation_sha256'],
           'original_shadow':str(a.original_adapter),'api_base':a.api_base,'preflight':preflight_info,
           'mode':'probe' if a.model_probe_only else 'pilot_tap' if a.pilot_one_tap else 'real_run',
           'dwell_ms':a.dwell_ms,'swipe_ms':a.swipe_ms,'allow_text':a.allow_text,'allow_adb_key':a.allow_adb_key})
    print('AGENT: MAI-UI-8B (official MAIUINaivigationAgent)',flush=True)
    print('ENDPOINT:',a.api_base,flush=True)
    print('SCREENSHOTS transmitted to the configured vLLM server. Raw screenshots and actions saved locally.',flush=True)
    print('TYPE-B ONLY for Tap/Swipe; ADBKeyboard/text and BACK/ENTER optional, separately recorded.',flush=True)
    if a.model_probe_only:
        msg='Type YES to approve ONE real phone screenshot sent to the model (NO PHONE ACTIONS): '
    else:
        msg='Type YES to authorize this one MAI-UI task on your Android phone (no purchases/messages/settings): '
    if input(msg).strip()!='YES':
        print('Not authorized; no model request or touch.');return 1
    sh=None;failure=None;termination=None;model_steps=0;actions=0;non_touch_streak=0;final_shadow=None
    try:
        v3=None;params=None
        if not a.model_probe_only:
            v3,params=original.load_v3(a.project)
            sh=_attach_live_p74_to_original_v3_shadow(original.Shadow(a.project,adb,a.remote_binary,outdir/'raw_getevent.txt',outdir,v3,params,a.dwell_ms,a.swipe_ms),a.project,outdir)
            sh.start()
        for step in range(1,2 if a.model_probe_only else a.max_steps+1):
            if not a.model_probe_only and actions>=a.max_actions:
                termination='action_budget';break
            # Recheck package BEFORE every screenshot; no unrelated apps or cross-app control.
            check=subprocess.run(adb+['shell','dumpsys','window'],capture_output=True,text=True,timeout=20)
            focused=next((s for s in check.stdout.splitlines() if 'mCurrentFocus=' in s),'')
            if APP_PACKAGE not in focused:
                raise RuntimeError('QQ Music no longer foreground; refusing cross-app execution: '+focused.strip())
            png=screenshot(adb)
            snap=outdir/f'step_{step:03d}_before.png';snap.write_bytes(png)
            pic=Image.open(io.BytesIO(png)).convert('RGB')
            if pic.size!=SCREEN:
                raise RuntimeError('Observed screenshot resolution changed: '+repr(pic.size))
            print(f'\nMAI-UI step={step}: official agent.predict(); screenshot={snap.name}',flush=True)
            prediction,model_action=agent.predict(a.task,{'screenshot':pic})
            model_steps+=1
            (outdir/f'step_{step:03d}_response.txt').write_text(str(prediction),encoding='utf-8')
            jappend(outdir/'agent_steps.jsonl',{'step':step,'model_prediction':prediction,'model_action':model_action,'screenshot':snap.name,'stage':'predicted'})
            if not isinstance(model_action,dict) or model_action.get('action') is None:
                raise RuntimeError('Official MAI returned an invalid/empty action: '+str(prediction)[-400:])
            plan=map_action(model_action,a.pilot_one_tap)
            jappend(outdir/'agent_steps.jsonl',{'step':step,'plan':plan,'stage':'validated'})
            print('MAI action:',json.dumps(model_action,ensure_ascii=False),flush=True)
            print('Adapter:',str(plan),flush=True)
            if a.model_probe_only:
                termination='model_probe_no_touch';break
            if plan['kind'] in ('typeb_tap','typeb_swipe') and actions>=a.max_actions:
                termination='action_budget';break
            if plan['kind'] in ('typeb_tap','typeb_swipe'):
                # Do not tap Android status/nav strip when model grounding is unreliable.
                x,y=plan['start']
                if y<55 or y>=2320:raise RuntimeError('MAI target inside Android system bar, no action executed: '+str((x,y)))
            n,desc=execute_plan(plan,sh,adb,model_action,a)
            actions+=n
            if n==0:non_touch_streak+=1
            else:non_touch_streak=0
            jappend(outdir/'agent_steps.jsonl',{'step':step,'plan':plan,'execution':desc,'typeb_delta':n,
                                                'typeb_total':actions,'stage':'executed'})
            print(f'  MAI execution: {desc}; Type-B gestures={actions}',flush=True)
            if plan['kind']=='terminate':termination='model_terminate_'+plan['status'];break
            if plan['kind']=='answer':termination='model_answer';break
            if a.pilot_one_tap:termination='pilot_one_tap_finished';break
            if non_touch_streak>=3:termination='non_touch_loop_limit';break
            time.sleep(a.request_interval)
        if termination is None:termination='max_steps'
        if sh is not None:final_shadow=sh.final()
    except KeyboardInterrupt:
        failure='KeyboardInterrupt';termination='user_stopped'
    except Exception as e:
        failure=type(e).__name__+': '+str(e)
        print('MAI-UI RUN STOPPED:',failure,flush=True)
        (outdir/'error_traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
        termination='error'
    finally:
        if sh is not None:
            if final_shadow is None:
                try:final_shadow=sh.final()
                except Exception as e:failure=(failure or '')+' | shadow_final_error: '+str(e)
            sh.stop()
        summary={'agent':'MAI-UI-8B','task':a.task,'model_steps':model_steps,'typeb_actions':actions,
                 'stop_reason':termination,'error':failure,'v3_final':final_shadow,
                 'task_success':'unverified (MAI model assertion is NOT ground truth)',
                 'outdir':str(outdir)}
        jdump(outdir/'summary.json',summary)
        print('MAI-UI RUN RESULT:',json.dumps(summary,ensure_ascii=False,default=str),flush=True)
    return 0 if failure is None else 2


if __name__=='__main__':
    try:raise SystemExit(cli())
    except (RuntimeError,FileNotFoundError,ValueError) as e:
        print('MAI-UI PREFLIGHT/CLI FATAL:',type(e).__name__+': '+str(e),file=sys.stderr)
        raise SystemExit(2)