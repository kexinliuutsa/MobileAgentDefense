#!/usr/bin/env python3
"""
FINAL FROZEN V1 + V2 + V3 DEFENSE

Final verdict
-------------
    detected =
        V1_behavioral
        OR
        V2_temporal
        OR
        V3_action_interval

V3
--
For each session:
    interval_violation_rate
        = (# action intervals >= AHB task-cluster interval threshold)
          / (# valid non-negative action intervals)

    V3 detects Agent iff:
        interval_violation_rate >= 0.6666666666666667

Everything below is frozen for subsequent black-box experiments.

IMPORTANT
---------
- V1 is loaded from the original frozen V1 initialization.
- V2 is loaded from defense_v2_temporal_policy.joblib.
- V3 task-cluster interval thresholds are frozen constants copied from the
  AHB author rule artifacts used in the final evaluation.
- No attack data is used at inference time.
- Black-box attacker should receive ONLY the final boolean verdict.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import re
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]

AHB_ROOT = Path(
    os.environ.get(
        "AHB_ROOT",
        str(
            Path.home()
            / "Desktop"
            / "Passing-the-Turing-Test-on-Screen-Agent-Humanization-Benchmark-main"
        ),
    )
).expanduser().resolve()

if not AHB_ROOT.exists():
    raise FileNotFoundError(
        f"AHB repo not found: {AHB_ROOT}\n"
        "Set AHB_ROOT explicitly."
    )

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(AHB_ROOT))

from src.heads.temporal_shape import timing_shape  # noqa: E402
from analysis.lib.feature_library import startT_us, endT_us  # noqa: E402


V1_SRC = (
    ROOT
    / "evaluation"
    / "run_blackbox_attack.py"
)

V2_BUNDLE = (
    ROOT
    / "results"
    / "defense_v2_temporal_policy.joblib"
)

# Only used to recover the fixed AHB task-cluster label for each released
# benchmark session. The candidate trajectory itself never changes cluster.
CLUSTER_LOOKUP_CSV = (
    ROOT
    / "results"
    / "ahb_cheap_layer"
    / "session_predictions.csv"
)


# =============================================================================
# FROZEN V3 PARAMETERS
# =============================================================================

# IMPORTANT:
# Do NOT replace this with 2.0 / 3.0.
# That produces 0.6666666666666666 and changes tied decisions.
V3_INTERVAL_RATE_THRESHOLD = 0.6666666666666667

# Exact author interval thresholds used in the final experiment.
# Units: microseconds.
V3_INTERVAL_THRESHOLDS_US = {
    0: 6311961.0,
    1: 6008676.0,
    2: 5927296.0,
    3: 5957152.0,
    4: 5670071.0,
}

EXPECTED_V2_VERSION = (
    "defense-v2-temporal-nested-v4-frozen"
)


# =============================================================================
# HELPERS
# =============================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def rec_get(
    record,
    key,
    default=None,
):
    if isinstance(record, dict):
        return record.get(
            key,
            default,
        )

    return getattr(
        record,
        key,
        default,
    )


def participant(record) -> str:
    return str(
        rec_get(
            record,
            "participant",
            "UNKNOWN",
        )
    )


def session_id(record) -> str:
    return str(
        rec_get(
            record,
            "session_id",
            "UNKNOWN",
        )
    )


def valid_gestures(record) -> list:
    out = []

    for gesture in rec_get(
        record,
        "gestures",
        [],
    ):
        if gesture is None:
            continue

        try:
            if (
                len(gesture) > 0
                and
                hasattr(
                    gesture[0],
                    "timestamp_us",
                )
            ):
                out.append(
                    gesture
                )
        except TypeError:
            pass

    return out


def gesture_matrix(record) -> np.ndarray:
    gestures = valid_gestures(
        record
    )

    if not gestures:
        return np.zeros(
            (0, 50),
            dtype=float,
        )

    rows = []

    for gesture in gestures:
        x = np.asarray(
            timing_shape(
                gesture
            ),
            dtype=float,
        ).reshape(-1)

        if x.shape != (50,):
            raise RuntimeError(
                f"timing_shape shape={x.shape}, "
                "expected (50,)"
            )

        rows.append(
            x
        )

    return np.vstack(
        rows
    )


def mean_session_margin(
    model,
    record,
) -> float:
    X = gesture_matrix(
        record
    )

    if len(X) == 0:
        return float("-inf")

    margins = model.decision_function(
        X
    )

    return float(
        np.mean(
            margins
        )
    )


# =============================================================================
# FROZEN V1 LOADER
# =============================================================================

def load_frozen_v1_prefix():
    """
    Execute only the initialization / frozen-scoring prefix of
    evaluation/run_blackbox_attack.py.

    The original attack loop is NEVER executed.
    """

    if not V1_SRC.exists():
        raise FileNotFoundError(
            V1_SRC
        )

    text = V1_SRC.read_text(
        encoding="utf-8"
    )

    marker = re.search(
        r"(?m)^for\s+attack_number\s*,\s*record_index\s+in\s+enumerate\(\s*$",
        text,
    )

    if marker is None:
        raise RuntimeError(
            "Could not locate frozen V1 "
            "attack-loop marker."
        )

    ns = {
        "__name__":
            "__main__",

        "__file__":
            str(V1_SRC),
    }

    capture = io.StringIO()
    old_cwd = Path.cwd()

    try:
        os.chdir(
            ROOT
        )

        with contextlib.redirect_stdout(
            capture
        ):
            exec(
                compile(
                    text[
                        :marker.start()
                    ],
                    str(V1_SRC),
                    "exec",
                ),
                ns,
                ns,
            )

    finally:
        os.chdir(
            old_cwd
        )

    return ns


# =============================================================================
# FINAL DEFENSE
# =============================================================================

class FrozenV1V2V3Defense:

    def __init__(self):

        # -------------------------------------------------------------
        # V2 bundle
        # -------------------------------------------------------------

        if not V2_BUNDLE.exists():
            raise FileNotFoundError(
                V2_BUNDLE
            )

        self.v2_bundle = joblib.load(
            V2_BUNDLE
        )

        version = self.v2_bundle.get(
            "policy_version"
        )

        if (
            version
            !=
            EXPECTED_V2_VERSION
        ):
            raise RuntimeError(
                "Unexpected frozen V2 version: "
                f"{version!r}"
            )

        if self.v2_bundle.get(
            "threshold_selection_uses_attack_condition",
            True,
        ):
            raise RuntimeError(
                "Frozen V2 provenance says "
                "attack data selected threshold."
            )

        self.policies = (
            self.v2_bundle[
                "policies"
            ]
        )

        # -------------------------------------------------------------
        # V1 hash regression
        # -------------------------------------------------------------

        current_hash = sha256_file(
            V1_SRC
        )

        frozen_hash = (
            self.v2_bundle.get(
                "v1_source_sha256"
            )
        )

        if (
            frozen_hash is not None
            and
            current_hash
            !=
            frozen_hash
        ):
            raise RuntimeError(
                "FROZEN V1 SOURCE HASH CHANGED.\n"
                f"bundle:  {frozen_hash}\n"
                f"current: {current_hash}"
            )

        self.v1_source_sha256 = (
            current_hash
        )

        # -------------------------------------------------------------
        # Frozen V1 helpers
        # -------------------------------------------------------------

        self.ns = (
            load_frozen_v1_prefix()
        )

        self.inner = self.ns.get(
            "namespace",
            {},
        )

        self.score_condition = (
            self.ns.get(
                "score_condition"
            )
        )

        self.get_gestures = (
            self.ns.get(
                "get_gestures"
            )
        )

        self.replace_gestures = (
            self.ns.get(
                "replace_gestures"
            )
        )

        if self.score_condition is None:
            raise RuntimeError(
                "Frozen V1 score_condition "
                "not found."
            )

        if self.get_gestures is None:
            raise RuntimeError(
                "Frozen V1 get_gestures "
                "not found."
            )

        if self.replace_gestures is None:
            raise RuntimeError(
                "Frozen V1 replace_gestures "
                "not found."
            )

        # -------------------------------------------------------------
        # Task-cluster lookup
        # -------------------------------------------------------------

        self.cluster_lookup = (
            self._load_cluster_lookup()
        )


    # =================================================================
    # CLUSTER
    # =================================================================

    def _load_cluster_lookup(
        self,
    ) -> dict:

        if not CLUSTER_LOOKUP_CSV.exists():
            raise FileNotFoundError(
                "Missing frozen task-cluster lookup:\n"
                f"{CLUSTER_LOOKUP_CSV}\n"
                "Run "
                "evaluation/run_ahb_cheap_layer_ablation_fixed.py "
                "once first."
            )

        df = pd.read_csv(
            CLUSTER_LOOKUP_CSV,
            low_memory=False,
        )

        required = {
            "participant",
            "session_id",
            "task_cluster",
        }

        missing = (
            required
            -
            set(df.columns)
        )

        if missing:
            raise RuntimeError(
                "Cluster lookup missing: "
                f"{sorted(missing)}"
            )

        lookup = {}

        for r in df[
            [
                "participant",
                "session_id",
                "task_cluster",
            ]
        ].drop_duplicates().itertuples(
            index=False
        ):

            key = (
                str(r.participant),
                str(r.session_id),
            )

            cid = int(
                r.task_cluster
            )

            if (
                key in lookup
                and
                lookup[key] != cid
            ):
                raise RuntimeError(
                    "Conflicting task cluster "
                    f"for {key}: "
                    f"{lookup[key]} vs {cid}"
                )

            lookup[key] = cid

        return lookup


    def resolve_task_cluster(
        self,
        record,
        task_cluster=None,
    ) -> int:

        if task_cluster is not None:
            cid = int(
                task_cluster
            )

        else:
            key = (
                participant(
                    record
                ),
                session_id(
                    record
                ),
            )

            if (
                key
                not in
                self.cluster_lookup
            ):
                raise RuntimeError(
                    "No frozen task-cluster "
                    f"mapping for {key}. "
                    "Pass task_cluster explicitly."
                )

            cid = int(
                self.cluster_lookup[
                    key
                ]
            )

        if (
            cid
            not in
            V3_INTERVAL_THRESHOLDS_US
        ):
            raise RuntimeError(
                "Unexpected task cluster: "
                f"{cid}"
            )

        return cid


    # =================================================================
    # V3
    # =================================================================

    def interval_violation_rate(
        self,
        record,
        task_cluster=None,
    ) -> dict:

        cid = (
            self.resolve_task_cluster(
                record,
                task_cluster,
            )
        )

        threshold_us = float(
            V3_INTERVAL_THRESHOLDS_US[
                cid
            ]
        )

        gestures = valid_gestures(
            record
        )

        total = 0
        violations = 0
        values = []

        prev_end = None

        for gesture in gestures:

            s = startT_us(
                gesture
            )

            e = endT_us(
                gesture
            )

            if (
                s is None
                or
                e is None
            ):
                continue

            s = float(s)
            e = float(e)

            if prev_end is not None:

                dt = (
                    s
                    -
                    prev_end
                )

                # Match AHB interval extractor:
                # only non-negative intervals.
                if dt >= 0:

                    total += 1

                    values.append(
                        float(dt)
                    )

                    if (
                        dt
                        >=
                        threshold_us
                    ):
                        violations += 1

            prev_end = e

        rate = (
            violations
            /
            total
            if total > 0
            else 0.0
        )

        detect = bool(
            rate
            >=
            V3_INTERVAL_RATE_THRESHOLD
        )

        return {
            "task_cluster":
                cid,

            "interval_threshold_us":
                threshold_us,

            "interval_total":
                int(total),

            "interval_violations":
                int(violations),

            "interval_violation_rate":
                float(rate),

            "v3_threshold":
                V3_INTERVAL_RATE_THRESHOLD,

            "v3_detect":
                detect,
        }


    # =================================================================
    # V1 + V2 + V3
    # =================================================================

    def score_record(
        self,
        record,
        *,
        task_cluster=None,
        v1_condition="Long Tap Author",
    ) -> dict:

        pid = participant(
            record
        )

        if (
            pid
            not in
            self.policies
        ):
            raise RuntimeError(
                "No frozen V2 policy "
                f"for participant {pid!r}"
            )

        # -------------------------
        # V1
        # -------------------------

        _, detail = (
            self.score_condition(
                v1_condition,
                [record],
                policy=(
                    "released_executor_rule"
                ),
            )
        )

        if len(detail) != 1:
            raise RuntimeError(
                "V1 expected exactly "
                "one session result."
            )

        v1_detect = bool(
            detail[
                "final_detect"
            ].iloc[0]
        )

        # -------------------------
        # V2
        # -------------------------

        policy = (
            self.policies[
                pid
            ]
        )

        temporal_model = (
            policy[
                "model"
            ]
        )

        temporal_threshold = float(
            policy[
                "threshold"
            ]
        )

        temporal_margin = (
            mean_session_margin(
                temporal_model,
                record,
            )
        )

        v2_temporal_detect = bool(
            temporal_margin
            >=
            temporal_threshold
        )

        v1v2_detect = bool(
            v1_detect
            or
            v2_temporal_detect
        )

        # -------------------------
        # V3
        # -------------------------

        v3 = (
            self.interval_violation_rate(
                record,
                task_cluster=task_cluster,
            )
        )

        # -------------------------
        # FINAL
        # -------------------------

        final_detect = bool(
            v1v2_detect
            or
            v3[
                "v3_detect"
            ]
        )

        return {
            "participant":
                pid,

            "session_id":
                session_id(
                    record
                ),

            "v1_detect":
                v1_detect,

            "v2_temporal_margin":
                float(
                    temporal_margin
                ),

            "v2_temporal_threshold":
                temporal_threshold,

            "v2_temporal_detect":
                v2_temporal_detect,

            "v1v2_detect":
                v1v2_detect,

            **v3,

            "v3_rescue":
                bool(
                    v3[
                        "v3_detect"
                    ]
                    and
                    not
                    v1v2_detect
                ),

            "final_detect":
                final_detect,
        }


    def detect_record(
        self,
        record,
        *,
        task_cluster=None,
        v1_condition="Long Tap Author",
    ) -> bool:
        """
        Public deployment decision.

        Returns ONLY:
            True  -> detected as Agent
            False -> escaped / Human-like
        """

        return bool(
            self.score_record(
                record,
                task_cluster=task_cluster,
                v1_condition=v1_condition,
            )[
                "final_detect"
            ]
        )


    # =================================================================
    # BLACK-BOX ORACLE
    # =================================================================

    def make_oracle(
        self,
        original_record,
        *,
        task_cluster=None,
        v1_condition="Long Tap Author",
    ):
        """
        Build a label-only oracle for one attack session.

        The attacker passes candidate_gestures and receives ONLY one bool.

        Metadata such as participant / task cluster remains fixed to the
        original session and cannot be mutated by the attacker.
        """

        cid = (
            self.resolve_task_cluster(
                original_record,
                task_cluster,
            )
        )

        state = {
            "queries":
                0,

            "last_diag":
                None,
        }

        def oracle(
            candidate_gestures,
        ):
            state[
                "queries"
            ] += 1

            candidate_record = (
                self.replace_gestures(
                    original_record,
                    candidate_gestures,
                )
            )

            diag = (
                self.score_record(
                    candidate_record,
                    task_cluster=cid,
                    v1_condition=v1_condition,
                )
            )

            state[
                "last_diag"
            ] = diag

            # CRITICAL:
            # attacker receives ONLY final 1-bit verdict.
            return bool(
                diag[
                    "final_detect"
                ]
            )

        # Runner may inspect these OFFLINE.
        # They are not returned to attack_session().
        oracle.state = state
        oracle.task_cluster = cid

        return oracle


    # =================================================================
    # MANIFEST
    # =================================================================

    def manifest(
        self,
    ) -> dict:

        return {
            "defense_version":
                "frozen-v1v2v3-action-interval-v1",

            "decision":
                "V1 OR V2 OR V3",

            "v1_source":
                str(
                    V1_SRC
                ),

            "v1_source_sha256":
                self.v1_source_sha256,

            "v2_bundle":
                str(
                    V2_BUNDLE
                ),

            "v2_policy_version":
                self.v2_bundle.get(
                    "policy_version"
                ),

            "v3_feature":
                "AHB action-interval violation rate",

            "v3_session_threshold":
                V3_INTERVAL_RATE_THRESHOLD,

            "v3_author_interval_thresholds_us":
                dict(
                    V3_INTERVAL_THRESHOLDS_US
                ),

            "threshold_selection":
                (
                    "Human-only 5% operating-point "
                    "calibration; no attack condition "
                    "used to select V3 threshold."
                ),
        }


# =============================================================================
# SELF TEST
# =============================================================================

def self_test():

    defense = (
        FrozenV1V2V3Defense()
    )

    ns = defense.ns
    inner = defense.inner

    long_records = list(
        ns.get(
            "long_records",
            inner.get(
                "long_records",
                [],
            ),
        )
    )

    if len(long_records) != 499:
        raise RuntimeError(
            "Expected 499 Long-Tap "
            f"records, got {len(long_records)}"
        )

    print(
        "=" * 100
    )

    print(
        "FROZEN V1+V2+V3 SELF TEST"
    )

    print(
        "=" * 100
    )

    print(
        "Long-Tap sessions:",
        len(long_records),
    )

    # Batch V1 for speed.
    _, detail = (
        defense.score_condition(
            "Long Tap Author",
            long_records,
            policy=(
                "released_executor_rule"
            ),
        )
    )

    if len(detail) != 499:
        raise RuntimeError(
            "Unexpected V1 detail size."
        )

    v1_count = int(
        detail[
            "final_detect"
        ].astype(bool).sum()
    )

    v1v2_count = 0
    v3_rescue_count = 0
    final_count = 0

    for i, record in enumerate(
        long_records
    ):

        pid = participant(
            record
        )

        policy = (
            defense.policies[
                pid
            ]
        )

        temporal_margin = (
            mean_session_margin(
                policy[
                    "model"
                ],
                record,
            )
        )

        temporal_detect = bool(
            temporal_margin
            >=
            float(
                policy[
                    "threshold"
                ]
            )
        )

        v1_detect = bool(
            detail[
                "final_detect"
            ].iloc[i]
        )

        v1v2 = bool(
            v1_detect
            or
            temporal_detect
        )

        v3 = (
            defense.interval_violation_rate(
                record
            )[
                "v3_detect"
            ]
        )

        final = bool(
            v1v2
            or
            v3
        )

        v1v2_count += int(
            v1v2
        )

        v3_rescue_count += int(
            v3
            and
            not
            v1v2
        )

        final_count += int(
            final
        )

    print(
        "V1:",
        f"{v1_count}/499",
    )

    print(
        "V1+V2:",
        f"{v1v2_count}/499",
    )

    print(
        "V3 rescue:",
        v3_rescue_count,
    )

    print(
        "FINAL:",
        f"{final_count}/499",
        f"= {final_count/499:.4%}",
    )

    # Exact regression values from the final frozen evaluation.
    assert v1_count == 382
    assert v1v2_count == 413
    assert v3_rescue_count == 72
    assert final_count == 485

    print(
        "\nSELF TEST: PASS"
    )

    print(
        "\nManifest:"
    )

    for k, v in (
        defense.manifest().items()
    ):
        print(
            f"  {k}: {v}"
        )


def main():

    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--self-test",
        action="store_true",
    )

    args = ap.parse_args()

    if args.self_test:
        self_test()

    else:
        defense = (
            FrozenV1V2V3Defense()
        )

        print(
            "Loaded:",
            defense.manifest()[
                "defense_version"
            ],
        )

        print(
            "V3 threshold:",
            V3_INTERVAL_RATE_THRESHOLD,
        )


if __name__ == "__main__":
    main()
