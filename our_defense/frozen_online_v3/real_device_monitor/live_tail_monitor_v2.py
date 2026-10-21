from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ahb_adapter import (
    events_to_record,
)

from evaluation.frozen_deployment_defense_clean import (
    FrozenV1V2V3Defense,
)

from response_policy_v2 import (
    CooldownResponsePolicy,
)


def to_jsonable(x):
    if hasattr(x, "item"):
        return x.item()
    if isinstance(x, dict):
        return {str(k): to_jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_jsonable(v) for v in x]
    return x


def score_prefix(
    defense,
    prefix,
    event,
    prefix_len,
    args,
):

    record = events_to_record(
        prefix,
        participant="live_agent",
        session_id=args.session_id,
    )

    n_gestures = len(record["gestures"])

    online_ready = bool(
        n_gestures >= args.min_touch_gestures
    )

    row = {
        "prefix_len": prefix_len,
        "timestamp_ns": event.get("timestamp_ns"),
        "action": event.get("action"),
        "n_gestures": n_gestures,
        "min_touch_gestures": args.min_touch_gestures,
        "online_ready": online_ready,
    }

    if not online_ready:

        row.update(
            {
                "score_status": "skipped_warmup",
                "latency_ms": 0.0,
                "v1_detect": None,
                "v2_detect": None,
                "v3_detect": None,
                "raw_final_detect": None,
                "online_final_detect": False,
            }
        )

        return row


    t0 = time.time()

    try:

        result = defense.score_record(
            record,
            task_cluster=args.task_cluster,
        )

        latency_ms = (time.time() - t0) * 1000

        raw_final_detect = bool(
            result["final_detect"]
        )

        online_final_detect = bool(
            online_ready
            and
            raw_final_detect
        )

        row.update(
            {
                "score_status": "ok",
                "latency_ms": latency_ms,
                "v1_detect": bool(result["v1_detect"]),
                "v2_detect": bool(result["v2_temporal_detect"]),
                "v3_detect": bool(result["v3_detect"]),
                "raw_final_detect": raw_final_detect,
                "online_final_detect": online_final_detect,
            }
        )

    except Exception as ex:

        latency_ms = (time.time() - t0) * 1000

        row.update(
            {
                "score_status": "error",
                "latency_ms": latency_ms,
                "v1_detect": None,
                "v2_detect": None,
                "v3_detect": None,
                "raw_final_detect": None,
                "online_final_detect": False,
                "error_type": type(ex).__name__,
                "error": str(ex),
                "traceback_last": traceback.format_exc().splitlines()[-1],
            }
        )

    return row


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--events",
        required=True,
    )

    parser.add_argument(
        "--out",
        required=True,
    )

    parser.add_argument(
        "--task-cluster",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--min-touch-gestures",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--friction-cooldown-prefixes",
        type=int,
        default=4,
    )

    parser.add_argument(
        "--poll-sec",
        type=float,
        default=0.2,
    )

    parser.add_argument(
        "--idle-timeout-sec",
        type=float,
        default=30.0,
    )

    parser.add_argument(
        "--session-id",
        default="live_tail_cooldown_session",
    )

    parser.add_argument(
        "--from-end",
        action="store_true",
    )

    args = parser.parse_args()

    events_path = Path(args.events)
    out_path = Path(args.out)

    out_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 80)
    print("LOADING FROZEN DEPLOYMENT DEFENSE")
    print("=" * 80)

    defense = FrozenV1V2V3Defense()

    response_policy = CooldownResponsePolicy(
        cooldown_prefixes=args.friction_cooldown_prefixes,
    )

    print("READY")
    print("watching:", events_path)
    print("writing:", out_path)
    print("cooldown_prefixes:", args.friction_cooldown_prefixes)
    print("Ctrl+C to stop")

    prefix = []
    prefix_len = 0
    last_event_time = time.time()

    offset = 0

    if args.from_end and events_path.exists():
        offset = events_path.stat().st_size

    with out_path.open("w") as fout:

        try:

            while True:

                if not events_path.exists():
                    time.sleep(args.poll_sec)
                    continue

                size = events_path.stat().st_size

                if size < offset:
                    offset = 0
                    prefix = []
                    prefix_len = 0

                    response_policy = CooldownResponsePolicy(
                        cooldown_prefixes=args.friction_cooldown_prefixes,
                    )

                if size == offset:

                    if (
                        time.time() - last_event_time
                        >
                        args.idle_timeout_sec
                    ):
                        print("idle timeout reached, stopping")
                        break

                    time.sleep(args.poll_sec)
                    continue

                with events_path.open("r") as f:
                    f.seek(offset)
                    new_lines = f.readlines()
                    offset = f.tell()

                for line in new_lines:

                    line = line.strip()

                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    prefix.append(event)
                    prefix_len += 1
                    last_event_time = time.time()

                    row = score_prefix(
                        defense=defense,
                        prefix=prefix,
                        event=event,
                        prefix_len=prefix_len,
                        args=args,
                    )

                    response = response_policy.decide(
                        row
                    )

                    row.update(
                        response
                    )

                    fout.write(
                        json.dumps(to_jsonable(row))
                        + "\n"
                    )

                    fout.flush()

                    print(
                        json.dumps(to_jsonable(row))
                    )

        except KeyboardInterrupt:
            print()
            print("stopped by user")

    print("saved:", out_path)


if __name__ == "__main__":
    main()
