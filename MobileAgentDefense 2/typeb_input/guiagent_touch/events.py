"""Read Linux getevent logs, retaining only our observed Type-B virtual input device.

Do not synthesize missing events. Event numbers are dynamically assigned by Android.
"""
import re

ADD = re.compile(rb'^\s*add device\s+\d+:\s+(/dev/input/event\d+)\s*$')
NAME = re.compile(rb'^\s*name:\s*"Virtual Touch Screen"')
EVT = re.compile(rb'^(\[\s*\d+\.\d+\])\s+(/dev/input/event\d+):\s+(.*)$')
TRACK = re.compile(rb'\bABS_MT_TRACKING_ID\s+([a-fA-F0-9]{8})\b')


def extract_virtual(raw: bytes):
    """Return virtual-device-only normalized log and observed device nodes."""
    pending, nodes = None, set()
    for line in raw.splitlines():
        m = ADD.match(line)
        if m:
            pending = m.group(1)
        elif NAME.match(line) and pending:
            nodes.add(pending)
    out = []
    for line in raw.splitlines():
        m = EVT.match(line)
        if m and m.group(2) in nodes:
            out.append(m.group(1) + b' ' + m.group(3) + b'\n')
    return b''.join(out), sorted(n.decode() for n in nodes)


def count_gestures(log: bytes):
    """Count completed Type-B contacts at a SYN_REPORT boundary."""
    live, committed_live, started, ended, complete = False, False, 0, 0, 0
    for line in log.splitlines():
        m = TRACK.search(line)
        if m:
            live = int(m.group(1), 16) != 0xffffffff
            if live:
                started += 1
            else:
                ended += 1
        if b'SYN_REPORT' in line:
            if committed_live and not live:
                complete += 1
            committed_live = live
    return {'tracking_down': started, 'tracking_up': ended,
            'complete_gestures': complete, 'unfinished': live,
            'alignment_pass': started == ended == complete and not live and complete > 0}
