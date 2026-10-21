"""P8C-compatible symbolic getevent parser. Only completed gestures are retained.
Coordinates preserve the verified P8C mixed decimal/hex convention. This is
single-contact replay, not a multi-slot multitouch decoder. Incomplete trailing
contacts are not synthesized. Read/decode errors propagate to the feature API.
"""
import math
import re
from pathlib import Path
from .adapter import Action, Event, to_native_session
TIME_RE = re.compile(r"\[\s*(\d+(?:\.\d+)?)\]")
X_RE = re.compile(r"ABS_MT_POSITION_X\s+([0-9a-fA-F]+)")
Y_RE = re.compile(r"ABS_MT_POSITION_Y\s+([0-9a-fA-F]+)")
TRACK_RE = re.compile(r"ABS_MT_TRACKING_ID\s+(-1|[0-9a-fA-F]+)")
BTN_RE = re.compile(r"BTN_TOUCH\s+(DOWN|UP|0+|0*1)", re.I)
def parse_num(x):
    x = str(x).strip()
    if not x:
        return 0
    if re.fullmatch(r"[0-9a-fA-F]+", x) and any(c in "abcdefABCDEF" for c in x):
        return int(x, 16)
    try:
        return int(x)
    except Exception:
        return int(x, 16)

def parse_gestures(path):
    gestures = []
    cur = None
    last_t = None
    x = None
    y = None

    lines = Path(path).read_text(encoding="utf-8", errors="strict").splitlines()

    for line in lines:
        mt = TIME_RE.search(line)
        if mt:
            last_t = float(mt.group(1))

        mx = X_RE.search(line)
        if mx:
            x = parse_num(mx.group(1))

        my = Y_RE.search(line)
        if my:
            y = parse_num(my.group(1))

        start_event = False
        end_event = False

        mtrack = TRACK_RE.search(line)
        if mtrack:
            val = mtrack.group(1).lower()
            if val == "ffffffff" or val == "-1":
                end_event = True
            else:
                start_event = True

        mbtn = BTN_RE.search(line)
        if mbtn:
            val = mbtn.group(1).upper()
            if val in {"DOWN", "1", "00000001"}:
                start_event = True
            elif val in {"UP", "0", "00000000"}:
                end_event = True

        if start_event and cur is None:
            cur = {"start_time": last_t, "points": []}

        if cur is not None and last_t is not None and x is not None and y is not None:
            pt = (last_t, x, y)
            if not cur["points"] or cur["points"][-1] != pt:
                cur["points"].append(pt)

        if end_event and cur is not None:
            pts = cur["points"]
            if pts:
                st = cur["start_time"] if cur["start_time"] is not None else pts[0][0]
                et = last_t if last_t is not None else pts[-1][0]
                duration = max(0.0, float(et) - float(st))

                sx, sy = pts[0][1], pts[0][2]
                ex, ey = pts[-1][1], pts[-1][2]

                path_len = 0.0
                for a, b in zip(pts, pts[1:]):
                    path_len += math.hypot(b[1] - a[1], b[2] - a[2])

                disp = math.hypot(ex - sx, ey - sy)
                mean_speed = path_len / duration if duration > 0 else 0.0

                gestures.append({
                    "start_time": st,
                    "end_time": et,
                    "duration": duration,
                    "n_points": len(pts),
                    "start_x": sx,
                    "start_y": sy,
                    "end_x": ex,
                    "end_y": ey,
                    "displacement": disp,
                    "path_length": path_len,
                    "mean_speed": mean_speed,
                    "points": pts,
                })

            cur = None

    if gestures:
        return gestures, "ok"
    return [], "no_completed_gesture"

def parse_log(log_path):
    gestures, status = parse_gestures(log_path)
    return {"parse_status": status, "gestures": gestures,
            "actions": to_native_session(gestures)}
