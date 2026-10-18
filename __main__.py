"""Minimal research CLI; requires one authorized ADB device and user-controlled phone."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from .events import extract_virtual, count_gestures

REMOTE = '/data/local/tmp/uinput_typeb_agent_compat'
SCREEN = (1080, 2400)


def run(args, timeout=30):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"Command failed: {args!r}\n{r.stderr.strip()}")
    return r.stdout


def adb():
    if not shutil.which('adb'):
        raise RuntimeError('adb not found. Install Android platform-tools.')
    rows = run(['adb', 'devices']).splitlines()[1:]
    serials = [f[0] for l in rows if len(f := l.split()) >= 2 and f[1] == 'device']
    if len(serials) != 1:
        raise RuntimeError(f'Expected exactly one authorized Android device, found {len(serials)}')
    return ['adb', '-s', serials[0]]


def size_check(a):
    dims = run(a + ['shell', 'wm', 'size'])
    sizes = re.findall(r'(?:Physical|Override) size:\s*(\d+)x(\d+)', dims)
    if not sizes or tuple(map(int, sizes[-1])) != SCREEN:
        raise RuntimeError(f'Fixed-axis prototype supports only 1080x2400; got {dims.strip()}')
    return dims.strip()


def check_bin(a):
    run(a + ['shell', 'test', '-x', REMOTE])


def action_args(ns):
    if ns.kind == 'tap':
        if not (0 <= ns.x < 1080 and 0 <= ns.y < 2400 and 50 <= ns.dwell <= 500):
            raise RuntimeError('Tap requires 0<=x<1080, 0<=y<2400 and dwell 50..500ms')
        if not 0 <= ns.jitter <= 25:
            raise RuntimeError('Tap jitter range 0..25px')
        return ['tap', str(ns.x), str(ns.y), str(ns.dwell), str(ns.jitter)]
    if not all((0 <= x < 1080 and 0 <= y < 2400) for x, y in ((ns.x1, ns.y1), (ns.x2, ns.y2))):
        raise RuntimeError('Swipe must remain within fixed 1080x2400 screen')
    if not 150 <= ns.duration <= 2000:
        raise RuntimeError('Swipe duration range 150..2000ms')
    if not 0 <= ns.curvature <= .5 or not 0 <= ns.overshoot <= 200:
        raise RuntimeError('Swipe curvature range 0..0.5, overshoot range 0..200')
    return ['swipe', *[str(i) for i in (ns.x1,ns.y1,ns.x2,ns.y2,ns.duration)],
            str(ns.curvature),ns.profile,str(ns.overshoot)]


def confirm(ns):
    if not ns.yes:
        raise RuntimeError('Refusing to touch device without --yes; visually verify target is harmless.')


def device_action(a, args):
    return run(a + ['shell', REMOTE] + args, timeout=40).strip()


def add_action_args(p, kind):
    p.set_defaults(kind=kind)
    if kind == 'tap':
        p.add_argument('x',type=int)
        p.add_argument('y',type=int)
        p.add_argument('--dwell',type=int,default=100)
        p.add_argument('--jitter',type=int,default=0)
    else:
        for n in ('x1','y1','x2','y2'):
            p.add_argument(n,type=int)
        p.add_argument('--duration',type=int,default=450)
        p.add_argument('--curvature',type=float,default=0)
        p.add_argument('--profile',choices=['linear','ease_in','ease_out','ease_in_out'],default='linear')
        p.add_argument('--overshoot',type=int,default=0)
    p.add_argument('--yes',action='store_true',help='Explicitly authorize one harmless touchscreen action')


def main():
    p=argparse.ArgumentParser(description='Research Type-B Android input executor (single device, 1080x2400)')
    sp=p.add_subparsers(dest='command', required=True)
    sp.add_parser('doctor',help='Read-only ADB and binary checks')
    for kind in ('tap','swipe'):
        add_action_args(sp.add_parser(kind),kind)
        add_action_args(sp.add_parser('probe-'+kind,help='Capture a single event-aligned gesture'),kind)
    for cmd in ('probe-tap','probe-swipe'):
        q=next(a for a in sp.choices.values() if a.prog.endswith(cmd))
        q.add_argument('--out',type=Path,default=Path('runs'))
    ns=p.parse_args()
    try:
        a=adb()
        screen=size_check(a)
        if ns.command=='doctor':
            try:
                check_bin(a); installed=True
            except RuntimeError:
                installed=False
            print(json.dumps({'device':a[-1],'display':screen,'remote_binary':REMOTE,
                              'installed':installed,'note':'No root assumed. Requires /dev/uinput shell access.'},indent=2))
            return
        check_bin(a)
        confirm(ns)
        args=action_args(ns)
        if not ns.command.startswith('probe-'):
            print(device_action(a,args)); return
        out=ns.out / datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        out.mkdir(parents=True,exist_ok=False)
        # All-device raw events are held only in an auto-deleted temporary directory.
        # The published output contains exclusively our observed virtual-device events.
        with tempfile.TemporaryDirectory() as scratch:
            rawpath=Path(scratch)/'getevent.tmp'
            with rawpath.open('wb') as f:
                mon=subprocess.Popen(a+['shell','getevent','-lt'],stdout=f,stderr=subprocess.STDOUT)
                try:
                    time.sleep(1.2)
                    if mon.poll() is not None:
                        raise RuntimeError('getevent exited before the action')
                    stdout=device_action(a,args)
                    time.sleep(.8)
                finally:
                    mon.terminate()
                    try:mon.wait(timeout=3)
                    except subprocess.TimeoutExpired:mon.kill();mon.wait(timeout=3)
            normalized, nodes=extract_virtual(rawpath.read_bytes())
        report=count_gestures(normalized)
        report.update({'nodes':nodes,'action':args,'executor_output':stdout,
                       'virtual_event_sha256':hashlib.sha256(normalized).hexdigest(),
                       'input_provenance':'uinput Type-B kernel virtual device; not human physical touch'})
        (out/'virtual_events_normalized.log').write_bytes(normalized)
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
        print('SAVED:',out)
        if not report['alignment_pass'] or report['complete_gestures'] != 1:
            raise RuntimeError('Gesture integrity failed (expected one complete gesture)')
    except (RuntimeError,subprocess.TimeoutExpired) as e:
        p.exit(2, f'ERROR: {e}\n')

if __name__=='__main__':
    main()
