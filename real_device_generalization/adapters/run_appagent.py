#!/usr/bin/env python3
"""Mac-only Tencent AppAgent deployment adapter: official prompts/action syntax,
real Android screenshots + UIA, validated Type-B gestures, original frozen V3.

No modification of original Open-AutoGLM runner, frozen V3 or Type-B binary.
The AppAgent decision loop is source-aligned with official scripts/task_executor.py
but this is an ADAPTER, not unmodified official AppAgent. Official prompt templates
are imported from the user's cloned TencentQQGYLab/AppAgent repo at runtime.

Minimal Python deps: pillow, requests. Android: ONE attached ADB device.
Requires validated original AutoGLM Type-B Shadow runner on Mac.
"""
from __future__ import annotations

import argparse
import ast
import base64
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

try:
    import requests
except ImportError:
    requests = None

TYPEB = '/data/local/tmp/uinput_typeb_agent_compat'
ORIGINAL_ADAPTER = Path.home() / 'Downloads' / 'RUN_AUTOGLM_V3_TYPEB_SHADOW_QQMUSIC.py'
PACKAGE = 'com.tencent.qqmusic'
SCREEN = (1080, 2400)
GRID_CELL = (135, 150)  # divides 1080x2400 -> 8x16
SUBAREAS = {
    'top-left': (.25,.25), 'top':(.50,.25), 'top-right':(.75,.25),
    'left':(.25,.50), 'center':(.50,.50), 'right':(.75,.50),
    'bottom-left':(.25,.75), 'bottom':(.50,.75), 'bottom-right':(.75,.75),
}


def append_jsonl(path: Path, row: dict):
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')


def adb_run(adb: list[str], *parts: str, timeout: int = 25, binary: bool = False):
    p = subprocess.run(adb + list(parts), capture_output=True, text=not binary, timeout=timeout)
    if p.returncode:
        msg = p.stderr if isinstance(p.stderr, str) else p.stderr.decode('utf-8','replace')
        raise RuntimeError('ADB failed: ' + msg[-400:])
    return p.stdout


def import_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise FileNotFoundError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def ensure_original_code(repo: Path):
    needed = [repo/'scripts'/'prompts.py', repo/'scripts'/'task_executor.py', repo/'scripts'/'and_controller.py']
    missing = [str(x) for x in needed if not x.is_file()]
    if missing:
        raise FileNotFoundError('Missing official AppAgent source: ' + repr(missing))
    return import_module(repo/'scripts'/'prompts.py', 'csg_official_appagent_prompts')


def parse_model_response(reply: str, grid: bool):
    """Parse AppAgent's official action grammar with presentation-only tolerance.

    Accept common Markdown/partially formatted replies, but never execute code:
    the final action must be one whitelisted AST call with literal arguments.
    Missing prose fields are logged, not invented. Raw replies are saved by run().
    """
    names = ('Observation', 'Thought', 'Action', 'Summary')
    fields = {n.lower(): '' for n in names}
    # GPT occasionally renders the official field labels in Markdown bold/bullets.
    header = re.compile(r'^\s*(?:>\s*)?(?:[-*]\s+)?(?:#{1,6}\s+)?'
                        r'(Observation|Thought|Action|Summary)\s*:\s*(.*)$', re.I)
    current = None
    for line in reply.splitlines():
        match = header.match(line.replace('**', ''))
        if match:
            current = match.group(1).lower()
            fields[current] = match.group(2).strip()
        elif current is not None:
            fields[current] += ('\n' if fields[current] else '') + line
    fields = {k: v.strip() for k,v in fields.items()}
    missing = [n for n in names if not fields[n.lower()]]
    expression = fields['action']
    if not expression:
        # Action-only fallback is allowed only when the ENTIRE reply is a call.
        # This cannot extract/execute suggested calls from arbitrary prose.
        candidate = reply.strip().strip('`').strip()
        if re.fullmatch(r'(?:FINISH|[a-z_][a-z_0-9]*\(.*\))', candidate, re.S):
            expression = candidate
        else:
            raise ValueError('Missing usable AppAgent Action; missing fields: '+', '.join(missing))
    original_expression = expression
    # Strip presentation wrappers, not content. Multiline programs fail AST check.
    expression = expression.strip()
    if expression.startswith('```'):
        code = re.fullmatch(r'```(?:python|text)?\s*\n?([\s\S]*?)\s*```', expression, re.I)
        if code:
            expression = code.group(1).strip()
    expression = expression.strip().strip('`').strip()
    if expression.startswith('**') and expression.endswith('**'):
        expression = expression[2:-2].strip()
    if expression == 'FINISH':
        return {'name':'FINISH','args':[],'fields':fields,'missing_fields':missing,
                'format_normalized':bool(missing or original_expression!=expression)}
    try:
        tree = ast.parse(expression, mode='eval').body
        if not isinstance(tree, ast.Call) or not isinstance(tree.func, ast.Name) or tree.keywords:
            raise ValueError('Invalid action call')
        name = tree.func.id
        args = [ast.literal_eval(x) for x in tree.args]
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError) as e:
        raise ValueError('Malformed AppAgent action: '+repr(expression[:250])) from e
    allowed = {
        False: {'tap':(int,), 'text':(str,), 'swipe':(int,str,str), 'grid':(), 'long_press':(int,)},
        True: {'tap':(int,str), 'swipe':(int,str,int,str), 'grid':(), 'long_press':(int,str)},
    }[grid]
    if name not in allowed:
        raise ValueError('Unsupported official AppAgent action: '+name)
    signatures = allowed[name]
    if len(args)!=len(signatures) or any(type(x) is not typ for x,typ in zip(args,signatures)):
        raise ValueError('Invalid arguments for AppAgent action: '+name)
    if name=='swipe' and not grid and (args[1] not in ('up','down','left','right') or args[2] not in ('short','medium','long')):
        raise ValueError('Invalid swipe direction/distance')
    if grid:
        for index in ([1] if name in ('tap','long_press') else [1,3] if name=='swipe' else []):
            if args[index] not in SUBAREAS:
                raise ValueError('Invalid grid subarea')
        if name in ('tap','long_press','swipe'):
            # Grid indices must be valid before translating to device coords.
            which = [0,2] if name=='swipe' else [0]
            for i in which:
                if not 1<=args[i]<=128:
                    raise ValueError('Grid label outside 1..128')
    return {'name':name,'args':args,'fields':fields,'missing_fields':missing,
            'format_normalized':bool(missing or original_expression!=expression)}


def png_screenshot(adb: list[str], output: Path):
    raw=adb_run(adb,'exec-out','screencap','-p',timeout=30,binary=True)
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise RuntimeError('Expected valid PNG from adb exec-out screencap')
    with Image.open(io.BytesIO(raw)) as img:
        if img.size != SCREEN:
            raise RuntimeError('Screen dimensions changed: '+str(img.size))
    output.write_bytes(raw)
    return output


def android_xml(adb: list[str], output: Path):
    """Read-only Android UI hierarchy; the official AppAgent uses UIAutomator."""
    remote='/sdcard/csg_appagent_ui.xml'
    adb_run(adb,'shell','uiautomator','dump',remote,timeout=35)
    adb_run(adb,'pull',remote,str(output),timeout=35)
    if not output.exists():
        raise RuntimeError('UIAutomator dump unavailable')
    return output.read_bytes()


def controls_from_xml(xml_raw: bytes, min_dist=30):
    """Official AppAgent-like union of clickable/focusable centers with MIN_DIST.
    Retains detection order; no UI documentation or previous exploration needed.
    """
    root=ET.fromstring(xml_raw)
    parents={child:parent for parent in root.iter() for child in parent}

    def uid(el):
        bounds=parse_bbox(el.attrib.get('bounds',''))
        (x1,y1),(x2,y2)=bounds
        rid=el.attrib.get('resource-id','')
        if rid: key=rid.replace(':','.').replace('/','_')
        else: key=el.attrib.get('class','Element')+f'_{x2-x1}_{y2-y1}'
        desc=el.attrib.get('content-desc','')
        if desc and len(desc)<20: key+='_'+desc.replace('/','_')
        return key

    def collect(attr):
        found=[]
        for el in root.iter():
            if el.attrib.get(attr)!='true': continue
            try: bbox=parse_bbox(el.attrib.get('bounds',''))
            except ValueError:continue
            (x1,y1),(x2,y2)=bbox
            if not (0<=x1<x2<=SCREEN[0] and 0<=y1<y2<=SCREEN[1]):continue
            mid=((x1+x2)//2,(y1+y2)//2)
            if any((mid[0]-e['xy'][0])**2+(mid[1]-e['xy'][1])**2<=min_dist**2 for e in found):continue
            try:
                parent=parents.get(el)
                key=(uid(parent)+'_' if parent is not None else '')+uid(el)
            except (KeyError, ValueError): key=el.attrib.get('class','Element')
            found.append({'xy':mid,'bbox':bbox,'key':key,'kind':attr})
        return found
    a,b=collect('clickable'),collect('focusable')
    for item in b:
        if not any((item['xy'][0]-e['xy'][0])**2+(item['xy'][1]-e['xy'][1])**2<=min_dist**2 for e in a):
            a.append(item)
    return a


def parse_bbox(s):
    m=re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]',s)
    if not m:raise ValueError('Invalid XML bounds')
    x1,y1,x2,y2=map(int,m.groups())
    if x1>=x2 or y1>=y2:raise ValueError('Invalid XML dimensions')
    return (x1,y1),(x2,y2)


def image_overlay(screenshot: Path, destination: Path, elements: list, grid: bool):
    with Image.open(screenshot) as orig:
        image=orig.convert('RGB')
    draw=ImageDraw.Draw(image)
    font=None
    for name in ('/System/Library/Fonts/Supplemental/Arial.ttf',
                 '/Library/Fonts/Arial.ttf', 'DejaVuSans.ttf'):
        try:
            font=ImageFont.truetype(name, 22)
            break
        except OSError: pass
    if font is None:
        try: font=ImageFont.load_default(size=22)
        except TypeError: font=ImageFont.load_default()
    if grid:
        cell_w,cell_h=GRID_CELL
        for r in range(SCREEN[1]//cell_h):
            for c in range(SCREEN[0]//cell_w):
                n=r*(SCREEN[0]//cell_w)+c+1
                x,y=c*cell_w,r*cell_h
                draw.rectangle((x,y,x+cell_w,y+cell_h),outline=(255,116,80),width=2)
                draw.rectangle((x+1,y+1,x+43,y+33),fill=(255,245,225))
                draw.text((x+3,y+3),str(n),font=font,fill=(30,30,30))
    else:
        for i,item in enumerate(elements,1):
            x,y=item['xy']
            draw.rectangle((x-26,y-17,x+27,y+18),fill=(22,22,22))
            draw.text((x-21,y-15),str(i),font=font,fill=(255,255,255))
    image.save(destination,format='PNG')
    return destination


def grid_xy(area: int, sub: str):
    cw,ch=GRID_CELL
    cols,rows=SCREEN[0]//cw,SCREEN[1]//ch
    if not (1<=area<=cols*rows):raise ValueError('Grid cell outside valid range')
    if sub not in SUBAREAS:raise ValueError('Unsupported subarea')
    i=area-1
    x=(i%cols)*cw+SUBAREAS[sub][0]*cw
    y=(i//cols)*ch+SUBAREAS[sub][1]*ch
    return int(x),int(y)


def element_xy(elements: list, label: int):
    if not (1<=label<=len(elements)):
        raise ValueError(f'Element label {label} out of range 1..{len(elements)}')
    return elements[label-1]['xy']


def swipe_endpoint(x:int,y:int,direction:str,dist:str):
    # AppAgent official controller: unit=width//10; medium=2*unit; long=3*unit;
    # vertical displacements use *2, horizontal use *1.
    unit=SCREEN[0]//10
    if dist=='medium':unit*=2
    elif dist=='long':unit*=3
    direction_xy={'up':(0,-2*unit),'down':(0,2*unit),
                  'left':(-unit,0),'right':(unit,0)}
    dx,dy=direction_xy[direction]
    x2=max(0,min(SCREEN[0]-1,x+dx))
    y2=max(0,min(SCREEN[1]-1,y+dy))
    return x2,y2


def api_call(model, key, url, prompt, image_path, max_tokens=450, timeout=90):
    if not key or not key.isascii() or any(c.isspace() for c in key):
        raise RuntimeError('OPENAI_API_KEY is missing or invalid: must be ASCII, no spaces')
    if requests is None:raise RuntimeError('Install requests: python3 -m pip install requests pillow')
    with Image.open(image_path) as im:
        buf=io.BytesIO()
        im.convert('RGB').save(buf,format='JPEG',quality=84)
    encoded=base64.b64encode(buf.getvalue()).decode('ascii')
    body={
        'model':model,
        'messages':[{'role':'user','content':[
            {'type':'text','text':prompt},
            {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+encoded}}
        ]}],
        'temperature':0.0,
        'max_tokens':max_tokens,
    }
    r=requests.post(url,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=body,timeout=(12,timeout))
    if not r.ok:
        try:e=r.json().get('error',{})
        except ValueError:e={'message':r.text[:200]}
        raise RuntimeError(f'GPT HTTP {r.status_code}: type={e.get("type")}, code={e.get("code")}, message={str(e.get("message"))[:250]}')
    reply=r.json()['choices'][0]['message']['content']
    if not isinstance(reply,str) or not reply.strip():raise RuntimeError('Empty GPT content')
    return reply, {'http_status':r.status_code,'request_id':r.headers.get('x-request-id'),
                   'usage':r.json().get('usage',{}),'model':r.json().get('model')}


def ensure_foreground(adb: list[str], expected_package: str):
    """Fail closed if the allowed app unexpectedly loses the foreground."""
    result=adb_run(adb,'shell','dumpsys','window',timeout=20)
    lines=[line.strip() for line in result.splitlines() if 'mCurrentFocus=' in line]
    focused=lines[0] if lines else 'UNKNOWN'
    if expected_package and expected_package not in focused:
        raise RuntimeError('APP FOREGROUND CHANGED: ' + focused[:250])
    return focused


def replace_text(adb: list[str], text: str):
    """Search-only repaired input semantics already used in MobileAgent-E pilot."""
    if not re.fullmatch(r'[A-Za-z0-9 ._\-]{1,160}',text):
        raise ValueError('Text adapter only permits ASCII search input; text may be unsafe/unsupported')
    adb_run(adb,'shell','input','keyevent','KEYCODE_MOVE_END')
    # In one shell call, avoid 160 separate ADB roundtrips.
    adb_run(adb,'shell','input','keyevent',*(['KEYCODE_DEL']*160),timeout=90)
    adb_run(adb,'shell','input','text',text.replace(' ','%s'),timeout=30)


def action_plan(parsed, grid, elements, last_action):
    name,args=parsed['name'],parsed['args']
    if name=='FINISH':return {'name':'FINISH'}
    if name=='grid':return {'name':'grid'}
    if name=='long_press':
        # Never silently emulate an unsupported or unvalidated touch primitive.
        raise RuntimeError('Official AppAgent long_press is not yet validated for this Type-B build; fail closed.')
    if name=='text':return {'name':'type','args':[args[0]]}
    if name=='tap':
        x,y=grid_xy(args[0],args[1]) if grid else element_xy(elements,args[0])
        return {'name':'tap','args':[x,y]}
    if name=='swipe':
        if grid:
            x,y=grid_xy(args[0],args[1]);xe,ye=grid_xy(args[2],args[3])
        else:
            x,y=element_xy(elements,args[0]);xe,ye=swipe_endpoint(x,y,args[1],args[2])
        if (x,y)==(xe,ye):raise ValueError('Zero-length swipe')
        return {'name':'swipe','args':[x,y,xe,ye]}
    raise RuntimeError('Unsupported action '+name)


def run(args):
    project=args.project.expanduser().resolve()
    repo=args.appagent_repo.expanduser().resolve()
    original_runner=args.original_runner.expanduser().resolve()
    prompts=ensure_original_code(repo)
    original=import_module(original_runner,'csg_validated_autoglm_shadow_appagent')
    for attr in ('adb_devices','verify_typeb_preflight','load_v3','Shadow'):
        if not hasattr(original,attr):raise RuntimeError('Original runner missing '+attr)
    adb=original.adb_devices()
    preflight=original.verify_typeb_preflight(project,adb,TYPEB,args.expected_package,verify_hash=True)
    commit='unavailable'
    q=subprocess.run(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True,text=True,timeout=8)
    if q.returncode==0:commit=q.stdout.strip()
    provenance={'agent':'Tencent AppAgent','repo':str(repo),'repo_commit':commit,
        'source':'official prompts/task flow; standalone Type-B adapter',
        'prompt_sha256':hashlib.sha256((repo/'scripts'/'prompts.py').read_bytes()).hexdigest(),
        'original_typeb_runner':str(original_runner), 'preflight':preflight,
        'model':args.model, 'api_base':args.api_base,
        'max_steps':args.max_steps,'request_interval':args.request_interval,
        'max_tokens':args.max_tokens,'text_semantics':'repaired replace-text',
        'long_press_supported':False,'expected_package':args.expected_package,
        'model_prompt_modifications':False, 'official_model_service_default':False,
        'adapter_version':'v1.1.0', 'ui_mode':args.ui_mode,
        'response_parser':'AST whitelist + markdown presentation normalization; missing prose field diagnostics'}
    if args.preflight_only:
        print('APPAGENT TYPE-B PRECHECK PASS',flush=True)
        print(json.dumps({k:v for k,v in provenance.items() if k not in ('preflight',)},ensure_ascii=False,indent=2),flush=True)
        print('No model calls, no touches, no V3 inference.',flush=True)
        return 0
    if not args.task:
        raise ValueError('Real run requires --task')
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key or not key.isascii() or not key.startswith('sk-') or any(c.isspace() for c in key):
        raise ValueError('Set a valid OPENAI_API_KEY in the Mac terminal; never paste it into chat')
    print('APPAGENT PILOT (Mac-only):',args.task)
    print('Official AppAgent prompts; GPT-4o; original Frozen V3; validated Type-B; safety approval required.')
    print('Screenshots are sent to OpenAI; task, screenshots, prompts, actions and detector results saved locally.')
    print('No buying, messaging, login, account changes, or sensitive operations.')
    if input('Type YES to authorize this one AppAgent task on the Android phone: ').strip()!='YES':
        print('CANCELLED: no touch or API call');return 0
    outdir=project/'real_device_online'/'appagent_typeb_shadow'/dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    outdir.mkdir(parents=True,exist_ok=False)
    (outdir/'run_config.json').write_text(json.dumps(provenance|{'task':args.task},ensure_ascii=False,indent=2))
    v3,params=original.load_v3(project)
    watcher=original.Shadow(project,adb,TYPEB,outdir/'getevent_all_devices.log',outdir,v3,params,args.tap_ms,args.swipe_ms)
    trace=[]; n_actions=0; agent_steps=0; stop='max_steps'; error=None
    final={}; started=False; grid=(args.ui_mode=='grid'); summary={}
    try:
        watcher.start();started=True
        last_summary='None'
        for k in range(1,args.max_steps+1):
            agent_steps=k
            screenshot=png_screenshot(adb,outdir/f'step_{k:03d}.png')
            elems=[]
            ui_xml=None
            use_grid=grid
            if not use_grid:
                try:
                    ui_xml=android_xml(adb,outdir/f'ui_{k:03d}.xml')
                    elems=controls_from_xml(ui_xml)
                except Exception as e:
                    if args.ui_mode=='element':raise
                    print('UIA unavailable, switching to official AppAgent grid prompt:',str(e)[:150])
                    use_grid=True
                if not elems and not use_grid:
                    if args.ui_mode=='element':raise RuntimeError('Zero UI elements; use --ui-mode grid')
                    use_grid=True
            overlay=image_overlay(screenshot,outdir/f'step_{k:03d}_model_view.png',elems,use_grid)
            if use_grid:
                prompt=prompts.task_template_grid
            else:
                prompt=prompts.task_template.replace('<ui_document>','')
            prompt=prompt.replace('<task_description>',args.task).replace('<last_act>',last_summary)
            (outdir/f'step_{k:03d}_prompt.txt').write_text(prompt,encoding='utf-8')
            raw,api=api_call(args.model,key,args.api_base,prompt,overlay,args.max_tokens,args.api_timeout)
            (outdir/f'step_{k:03d}_response.txt').write_text(raw,encoding='utf-8')
            try:
                parsed=parse_model_response(raw,grid=use_grid)
            except ValueError:
                print('RAW MODEL RESPONSE SAVED:',str(outdir/f'step_{k:03d}_response.txt'),flush=True)
                print('RAW RESPONSE PREVIEW:',repr(raw[:500]),flush=True)
                raise
            if parsed['missing_fields']:
                print('APPAGENT OUTPUT FORMAT WARNING: missing', ', '.join(parsed['missing_fields']),
                      '(raw response retained; only strict action grammar executed)',flush=True)
            intended=action_plan(parsed,use_grid,elems,last_summary)
            row={'step':k,'appagent_action':parsed['name'],'arguments':parsed['args'],
                 'hardware_action':intended,'grid':use_grid,'ui_element_count':len(elems),
                 'parser_missing_fields':parsed['missing_fields'],'parser_format_normalized':parsed['format_normalized'],
                 'screenshot':screenshot.name,'model_view':overlay.name,'prompt_file':f'step_{k:03d}_prompt.txt',
                 'response_file':f'step_{k:03d}_response.txt','api':api,'hardware_g_before':watcher.last_n}
            print(f'APPAGENT step={k} action={parsed["name"]} args={parsed["args"]}',flush=True)
            if intended['name']=='FINISH':
                stop='agent_reported_finish'
                row['status']='agent_reported_finish_unverified'
                append_jsonl(outdir/'agent_steps.jsonl',row)
                break
            if intended['name']=='grid':
                grid=True;row['status']='grid_requested_no_touch'
                append_jsonl(outdir/'agent_steps.jsonl',row)
                continue
            name= intended['name']
            if n_actions>=args.max_actions:raise RuntimeError('Maximum action budget reached')
            row['foreground_before_action']=ensure_foreground(adb,args.expected_package)
            if name=='tap':
                x,y=intended['args']
                watcher.do('tap',x,y,args.tap_ms,0)
                row['prefixes']=watcher.score_new(1,'Tap')
            elif name=='swipe':
                x,y,xe,ye=intended['args']
                watcher.do('swipe',x,y,xe,ye,args.swipe_ms,0,'linear',0)
                row['prefixes']=watcher.score_new(1,'Swipe')
            elif name=='type':
                replace_text(adb,intended['args'][0])
                row['prefixes']=[]
            else:raise RuntimeError('Unsupported hardware action: '+name)
            n_actions+=1
            row['hardware_g_after']=watcher.last_n
            row['status']='executed'
            append_jsonl(outdir/'agent_steps.jsonl',row)
            trace.append(row)
            if parsed['fields']['summary']:
                last_summary=parsed['fields']['summary']
            grid=(args.ui_mode=='grid')  # official grid() is one-step escape hatch
            if args.request_interval and k<args.max_steps:time.sleep(args.request_interval)
    except KeyboardInterrupt:
        stop='user_interrupt';error='KeyboardInterrupt'
        print('STOPPED BY USER',flush=True)
    except Exception as exc:
        stop='error';error=f'{type(exc).__name__}: {exc}'
        print('APPAGENT STOPPED:',error,flush=True)
        traceback.print_exc(limit=8)
    finally:
        if started:
            try:final=watcher.final()
            except Exception as exc:final={'error':f'{type(exc).__name__}: {exc}'}
            try:watcher.stop()
            except Exception as exc:print('WARN: getevent stop failed:',exc,flush=True)
        events=[]
        if watcher.eventsfile.exists():
            events=[json.loads(line) for line in watcher.eventsfile.read_text().splitlines() if line.strip()]
        first_alarm=next((x['hardware_g'] for x in events if x.get('detected') is True),None)
        summary={'agent':'AppAgent','task':args.task,'model':args.model,
                 'agent_steps':agent_steps,'executed_actions':n_actions,
                 'hardware_gestures':final.get('hardware_gestures'),
                 'first_alarm_g':first_alarm,'online_detected':first_alarm is not None,
                 'v3_final':final,'stop_reason':stop,'error':error,
                 'task_success':'unverified (human review required)',
                 'outdir':str(outdir),'provenance':provenance}
        (outdir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str))
        print('APPAGENT RUN RESULT:',json.dumps({k:v for k,v in summary.items() if k!='provenance'},ensure_ascii=False,default=str),flush=True)
    return 0 if error is None else 2


def self_test():
    good=[
        ('Observation: x\nThought: y\nAction: tap(4)\nSummary: z',False,'tap',[4]),
        ('Observation: x\nThought: y\nAction: swipe(4, "up", "medium")\nSummary: z',False,'swipe',[4,'up','medium']),
        ('Observation: x\nThought: y\nAction: text("Eason Chan")\nSummary: z',False,'text',['Eason Chan']),
        ('Observation: x\nThought: y\nAction: grid()\nSummary: z',False,'grid',[]),
        ('Observation: x\nThought: y\nAction: tap(5, "center")\nSummary: z',True,'tap',[5,'center']),
        ('Observation: x\nThought: y\nAction: FINISH\nSummary: z',True,'FINISH',[]),
        ('**Observation:** x\n**Thought:** y\n**Action:** `swipe(92, "center", 36, "center")`\n**Summary:** z',True,'swipe',[92,'center',36,'center']),
        ('Action: `swipe(92, "center", 36, "center")`',True,'swipe',[92,'center',36,'center']),
        ('`swipe(92, "center", 36, "center")`',True,'swipe',[92,'center',36,'center']),
        ('Action: ```python\nswipe(92, "center", 36, "center")\n```',True,'swipe',[92,'center',36,'center']),

    ]
    for s,grid,name,args in good:
        got=parse_model_response(s,grid)
        assert got['name']==name and got['args']==args
    for bad in ['tap(__import__("os").system("false"))','swipe(1,"north","long")','tap(0,2)']:
        text=f'Observation: x\nThought: y\nAction: {bad}\nSummary: z'
        try:
            parsed=parse_model_response(text,False)
            if bad.startswith('tap(0,2)'):pass
            else:raise AssertionError('Malformed action parsed: '+bad)
        except ValueError:pass
    assert parse_model_response('Action: tap(4, "center")',True)['missing_fields']==['Observation','Thought','Summary']
    for badreply in [
        'Observation: x\nThought: y\nSummary: no Action here',
        'Do this: tap(5, "center")',
        'Action: __import__("os").system("whoami")',
        'Action: swipe(129, "center", 36, "center")',
        'Action: swipe(92, "center", 36, "center"); tap(1,"center")',
    ]:
        try:
            parse_model_response(badreply,True)
            raise AssertionError('Unsafe output accepted: '+badreply)
        except ValueError: pass
    assert grid_xy(1,'center')==(67,75)
    assert grid_xy(128,'center')==(1012,2325)
    assert swipe_endpoint(540,1200,'up','medium')==(540,768)
    root=b'<hierarchy><node clickable="true" bounds="[0,0][300,150]" class="android.widget.Button"/><node focusable="true" bounds="[0,0][300,150]" class="android.widget.Button"/></hierarchy>'
    assert len(controls_from_xml(root))==1
    print('APPAGENT OFFLINE SELF-TEST PASS (no phone actions, no API, no V3)')
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,default=Path.home()/'Desktop'/'GUI_AHB_PAPER_REBUILD')
    p.add_argument('--appagent-repo',type=Path,default=Path.home()/'Desktop'/'AppAgent')
    p.add_argument('--original-runner',type=Path,default=ORIGINAL_ADAPTER)
    p.add_argument('--task',default='')
    p.add_argument('--expected-package',default=PACKAGE)
    p.add_argument('--model',default='gpt-4o-2024-11-20')
    p.add_argument('--api-base',default='https://api.openai.com/v1/chat/completions')
    p.add_argument('--max-steps',type=int,default=8)
    p.add_argument('--max-actions',type=int,default=8)
    p.add_argument('--max-tokens',type=int,default=450)
    p.add_argument('--api-timeout',type=int,default=90)
    p.add_argument('--request-interval',type=float,default=4.0)
    p.add_argument('--ui-mode',choices=['auto','element','grid'],default='auto')
    p.add_argument('--tap-ms',type=int,default=100)
    p.add_argument('--swipe-ms',type=int,default=450)
    p.add_argument('--preflight-only',action='store_true')
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--replay-response',type=Path,help='Offline-parse a saved AppAgent response, no ADB, API, or V3')
    a=p.parse_args()
    if a.self_test:return self_test()
    if a.replay_response:
        raw=a.replay_response.expanduser().read_text(encoding='utf-8')
        parsed=parse_model_response(raw,grid=(a.ui_mode=='grid'))
        print('APPAGENT OFFLINE RESPONSE REPLAY PASS')
        print(json.dumps({k:parsed[k] for k in ('name','args','missing_fields','format_normalized')},
                         ensure_ascii=False,indent=2))
        print('No API calls, no touches, no frozen-model inference.')
        return 0
    if not 1<=a.max_steps<=60 or not 1<=a.max_actions<=60:p.error('max-steps and max-actions must be 1..60')
    if not 50<=a.tap_ms<=500 or not 150<=a.swipe_ms<=2000:p.error('Type-B timing outside validated bounds')
    if not 0<=a.request_interval<=60:p.error('request-interval must be between 0 and 60 seconds')
    if not 100<=a.max_tokens<=2048:p.error('max-tokens must be 100..2048')
    return run(a)

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print('APPAGENT FATAL:',type(e).__name__+':',str(e),flush=True)
        traceback.print_exc(limit=6)
        sys.exit(2)