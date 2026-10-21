from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))



LAST_EVENT_NS = None


def stable_int(*parts, mod=2**32):
    s = "::".join(str(x) for x in parts)
    h = hashlib.sha256(s.encode()).hexdigest()
    return int(h[:12], 16) % mod


def pick(xs, *parts):
    return xs[stable_int(*parts, mod=len(xs))]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def run_adb(args, timeout=10):
    cmd = ["adb"] + [str(x) for x in args]
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(
            "ADB failed: "
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + p.stdout
            + "\nSTDERR:\n"
            + p.stderr
        )
    return p.stdout.strip()


def get_screen_size(default=(1080, 2400)):
    try:
        out = run_adb(["shell", "wm", "size"])
        m = re.search(r"(\d+)x(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return default


def gesture_duration_us(g):
    if len(g) < 2:
        return 1
    return max(1, int(g[-1].timestamp_us - g[0].timestamp_us))


def displacement(g):
    if len(g) < 2:
        return 0.0
    dx = g[-1].x - g[0].x
    dy = g[-1].y - g[0].y
    return (dx * dx + dy * dy) ** 0.5


def extract_history_timing_templates():
    cache = Path("results/real_device_monitor/human_timing_templates_v1.json")

    if cache.exists():
        data = json.loads(cache.read_text())

        print("=" * 80)
        print("LOAD HUMAN TIMING TEMPLATES FROM CACHE")
        print("=" * 80)
        print("cache:", cache)
        print("tap_ms samples:", len(data["tap_ms"]), data["tap_ms"][:10])
        print("swipe_ms samples:", len(data["swipe_ms"]), data["swipe_ms"][:10])
        print("gap_ms samples:", len(data["gap_ms"]), data["gap_ms"][:10])

        return data

    # Fallback: no old EXP49 loading, no gesture log scan.
    # This is still a command-level history-timing-style attack:
    # use human-like duration/gap ranges instead of fixed robotic timing.
    data = {
        "tap_ms": [55, 70, 85, 100, 120, 145, 170],
        "swipe_ms": [420, 520, 650, 780, 920, 1100, 1350, 1650],
        "gap_ms": [280, 380, 520, 700, 900, 1150, 1450, 1800],
    }

    print("=" * 80)
    print("LOAD FALLBACK HUMAN-LIKE TIMING TEMPLATES")
    print("=" * 80)
    print("No cache found:", cache)
    print("Using built-in templates; no defense or gesture logs loaded.")
    print("tap_ms samples:", len(data["tap_ms"]), data["tap_ms"])
    print("swipe_ms samples:", len(data["swipe_ms"]), data["swipe_ms"])
    print("gap_ms samples:", len(data["gap_ms"]), data["gap_ms"])

    return data


def append_event(path: Path, event: dict):
    global LAST_EVENT_NS

    now_ns = time.monotonic_ns()
    event["timestamp_ns"] = now_ns

    if LAST_EVENT_NS is None:
        event["gap_ns"] = None
    else:
        event["gap_ns"] = now_ns - LAST_EVENT_NS

    LAST_EVENT_NS = now_ns

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a") as f:
        f.write(json.dumps(event) + "\n")


def latest_risk_row(path: Path):
    if not path.exists():
        return None

    last = None

    with path.open("r") as f:
        for line in f:
            if line.strip():
                try:
                    last = json.loads(line)
                except Exception:
                    pass

    return last


def wait_monitor(path: Path, prefix_len: int, timeout_sec=10.0):
    start = time.time()

    while time.time() - start < timeout_sec:
        row = latest_risk_row(path)

        if row and int(row.get("prefix_len", -1)) >= prefix_len:
            return row

        time.sleep(0.2)

    return latest_risk_row(path)


def sleep_gap(templates, key, scale):
    gap_ms = pick(templates["gap_ms"], key)
    gap_ms = int(clamp(gap_ms * scale, 150, 2500))
    time.sleep(gap_ms / 1000.0)
    return gap_ms


def do_home(events_path, w, h, profile, step):
    run_adb(["shell", "input", "keyevent", "HOME"])

    append_event(
        events_path,
        {
            "action": "home",
            "screen_width": w,
            "screen_height": h,
            "profile": profile,
            "adaptive_step": step,
        },
    )


def do_back(events_path, w, h, profile, step):
    run_adb(["shell", "input", "keyevent", "BACK"])

    append_event(
        events_path,
        {
            "action": "back",
            "screen_width": w,
            "screen_height": h,
            "profile": profile,
            "adaptive_step": step,
        },
    )


def do_tap(events_path, x, y, duration_ms, w, h, profile, step):
    run_adb(["shell", "input", "tap", int(x), int(y)])

    append_event(
        events_path,
        {
            "action": "tap",
            "x": int(x),
            "y": int(y),
            "duration_ms": int(duration_ms),
            "screen_width": w,
            "screen_height": h,
            "profile": profile,
            "adaptive_step": step,
        },
    )


def do_swipe(events_path, x1, y1, x2, y2, duration_ms, w, h, profile, step):
    run_adb(
        [
            "shell",
            "input",
            "swipe",
            int(x1),
            int(y1),
            int(x2),
            int(y2),
            int(duration_ms),
        ],
        timeout=max(10, int(duration_ms / 1000) + 5),
    )

    append_event(
        events_path,
        {
            "action": "swipe",
            "direction": "page_down",
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2),
            "duration_ms": int(duration_ms),
            "screen_width": w,
            "screen_height": h,
            "profile": profile,
            "adaptive_step": step,
        },
    )


def print_monitor_state(prefix_len, action, row, extra):
    payload = {
        "event": prefix_len,
        "action": action,
        **extra,
        "monitor_response": None if row is None else row.get("response"),
        "online_detect": None if row is None else row.get("online_final_detect"),
        "n_gestures": None if row is None else row.get("n_gestures"),
    }

    print(json.dumps(payload))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--events", required=True)
    parser.add_argument("--risk-stream", required=True)
    parser.add_argument("--n-rounds", type=int, default=8)
    parser.add_argument("--gap-scale", type=float, default=1.0)
    parser.add_argument("--profile", default="history_timing_online")
    parser.add_argument("--wait-monitor", action="store_true")

    args = parser.parse_args()

    events_path = Path(args.events)
    risk_path = Path(args.risk_stream)

    templates = extract_history_timing_templates()

    w, h = get_screen_size()

    print("=" * 80)
    print("START HISTORY_TIMING ONLINE RUNNER")
    print("=" * 80)
    print("screen:", w, h)
    print("events:", events_path)
    print("risk:", risk_path)

    tap_points = [
        (0.50, 0.55),
        (0.42, 0.62),
        (0.58, 0.60),
        (0.50, 0.68),
    ]

    prefix_len = 0
    step = 0

    do_home(events_path, w, h, args.profile, step)
    prefix_len += 1
    time.sleep(1.0)

    for r in range(args.n_rounds):
        step += 1

        gap_ms = sleep_gap(
            templates,
            key=("tap_gap", r),
            scale=args.gap_scale,
        )

        tx, ty = tap_points[r % len(tap_points)]
        x = int(w * tx)
        y = int(h * ty)

        tap_duration_ms = pick(
            templates["tap_ms"],
            "tap_duration",
            r,
        )

        do_tap(
            events_path,
            x,
            y,
            tap_duration_ms,
            w,
            h,
            args.profile,
            step,
        )

        prefix_len += 1

        row = wait_monitor(risk_path, prefix_len) if args.wait_monitor else None

        print_monitor_state(
            prefix_len,
            "tap",
            row,
            {
                "round": r,
                "tap_duration_ms": tap_duration_ms,
                "gap_before_ms": gap_ms,
            },
        )

        step += 1

        gap_ms = sleep_gap(
            templates,
            key=("swipe_gap", r),
            scale=args.gap_scale,
        )

        swipe_duration_ms = pick(
            templates["swipe_ms"],
            "swipe_duration",
            r,
        )

        do_swipe(
            events_path,
            int(w * 0.50),
            int(h * 0.78),
            int(w * 0.50),
            int(h * 0.35),
            swipe_duration_ms,
            w,
            h,
            args.profile,
            step,
        )

        prefix_len += 1

        row = wait_monitor(risk_path, prefix_len) if args.wait_monitor else None

        print_monitor_state(
            prefix_len,
            "swipe",
            row,
            {
                "round": r,
                "swipe_duration_ms": swipe_duration_ms,
                "gap_before_ms": gap_ms,
            },
        )

    step += 1

    sleep_gap(
        templates,
        key="back_gap",
        scale=args.gap_scale,
    )

    do_back(events_path, w, h, args.profile, step)
    prefix_len += 1

    row = wait_monitor(risk_path, prefix_len) if args.wait_monitor else None

    print_monitor_state(
        prefix_len,
        "back",
        row,
        {},
    )

    print("=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
