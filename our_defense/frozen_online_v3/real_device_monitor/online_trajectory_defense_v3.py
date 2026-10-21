#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from real_device_monitor.dynamic_probe_runtime_v2 import (
    DynamicProbeRuntimeV2,
    clean_v1_score_condition,
)


START_G = 11
STOP_G = 16


CALIBRATION_ARTIFACT = (
    ROOT
    / "evaluation"
    / "frozen_evidence_regions_v1.json"
)


class OnlineTrajectoryDefenseV3:
    """
    Core interface:

        trajectory prefix
            ->
        behavioral evidence
            ->
        Human calibration
            ->
        stability resolution
            ->
        response

    Runtime inputs:
        trajectory only

    task_cluster is accepted only for compatibility
    with the frozen legacy scorer. It is NOT used by
    the strict calibration policy itself.
    """

    VERSION = (
        "online-trajectory-defense-v3"
    )

    def __init__(self):

        self.runtime_v2 = (
            DynamicProbeRuntimeV2()
        )

        artifact = json.loads(
            CALIBRATION_ARTIFACT.read_text()
        )

        if bool(
            artifact.get(
                "attack_data_used_for_calibration",
                True,
            )
        ):

            raise RuntimeError(
                "Evidence calibration "
                "must be Human-only."
            )

        self.tau_low = float(
            artifact[
                "tau_low"
            ][
                "threshold"
            ]
        )

        self.tau_high = float(
            artifact[
                "tau_high"
            ][
                "threshold"
            ]
        )

        if not (
            math.isfinite(
                self.tau_low
            )
            and
            math.isfinite(
                self.tau_high
            )
            and
            self.tau_low
            <
            self.tau_high
        ):

            raise RuntimeError(
                "Invalid evidence thresholds."
            )

    # ============================================================
    # Evidence
    # ============================================================

    def _strict_score(
        self,
        record,
        gestures,
    ):

        scored_record = (
            self.runtime_v2
            ._record_with_gestures(
                record,
                gestures,
            )
        )

        _, detail = (
            clean_v1_score_condition(
                "Long Tap Author",
                [
                    scored_record
                ],
                policy=
                    "released_executor_rule",
            )
        )

        if len(detail) != 1:

            raise RuntimeError(
                "Expected exactly one "
                "strict-score row."
            )

        score = float(
            detail[
                "strict_score"
            ].iloc[0]
        )

        if not math.isfinite(
            score
        ):

            raise RuntimeError(
                "Non-finite strict score."
            )

        return score

    def _base_evidence(
        self,
        record,
        gestures,
        task_cluster,
    ):

        base = (
            self.runtime_v2
            ._score(
                record=
                    record,

                gestures=
                    gestures,

                task_cluster=
                    task_cluster,
            )
        )

        return {
            "v1":
                bool(
                    base[
                        "v1_detect"
                    ]
                ),

            "v2":
                bool(
                    base[
                        "v2_temporal_detect"
                    ]
                ),

            "v3":
                bool(
                    base[
                        "v3_detect"
                    ]
                ),

            "legacy_final":
                bool(
                    base[
                        "final_detect"
                    ]
                ),
        }

    # ============================================================
    # Calibration
    # ============================================================

    def _region(
        self,
        score,
    ):

        if score >= self.tau_high:
            return "HIGH"

        if score >= self.tau_low:
            return "UNCERTAIN"

        return "LOW"

    # ============================================================
    # Negative-side CF stability
    #
    # This is valid ONLY when current V1 is benign.
    # ============================================================

    def _cf_stability(
        self,
        record,
        gestures,
        task_cluster,
    ):

        g = len(
            gestures
        )

        positions = list(
            range(
                START_G,
                min(
                    g,
                    STOP_G,
                )
                +
                1,
            )
        )

        t1 = time.perf_counter_ns()

        stage1 = (
            self.runtime_v2
            ._probe_positions(
                record=
                    record,

                prefix=
                    gestures,

                positions=
                    positions,

                bank=
                    self.runtime_v2
                    .sparse_bank,

                task_cluster=
                    task_cluster,
            )
        )

        stage1_ms = (
            time.perf_counter_ns()
            -
            t1
        ) / 1e6

        fragile = bool(
            stage1[
                "flips"
            ]
            >
            0
        )

        if not fragile:

            return {
                "checked":
                    True,

                "fragile":
                    False,

                "confirmed":
                    False,

                "stage1_flips":
                    int(
                        stage1[
                            "flips"
                        ]
                    ),

                "stage2_flips":
                    0,

                "stage1_positions":
                    list(
                        stage1[
                            "fragile_positions"
                        ]
                    ),

                "stage2_positions":
                    [],

                "n_stage1_probes":
                    int(
                        stage1[
                            "n_probes"
                        ]
                    ),

                "n_stage2_probes":
                    0,

                "latency_stage1_ms":
                    stage1_ms,

                "latency_stage2_ms":
                    0.0,
            }

        t2 = time.perf_counter_ns()

        stage2 = (
            self.runtime_v2
            ._probe_positions(
                record=
                    record,

                prefix=
                    gestures,

                positions=
                    stage1[
                        "fragile_positions"
                    ],

                bank=
                    self.runtime_v2
                    .dense_bank,

                task_cluster=
                    task_cluster,
            )
        )

        stage2_ms = (
            time.perf_counter_ns()
            -
            t2
        ) / 1e6

        confirmed = any(
            int(n)
            >=
            2
            for n in
            stage2[
                "position_flip_counts"
            ].values()
        )

        return {
            "checked":
                True,

            "fragile":
                True,

            "confirmed":
                bool(
                    confirmed
                ),

            "stage1_flips":
                int(
                    stage1[
                        "flips"
                    ]
                ),

            "stage2_flips":
                int(
                    stage2[
                        "flips"
                    ]
                ),

            "stage1_positions":
                list(
                    stage1[
                        "fragile_positions"
                    ]
                ),

            "stage2_positions":
                list(
                    stage2[
                        "fragile_positions"
                    ]
                ),

            "n_stage1_probes":
                int(
                    stage1[
                        "n_probes"
                    ]
                ),

            "n_stage2_probes":
                int(
                    stage2[
                        "n_probes"
                    ]
                ),

            "latency_stage1_ms":
                stage1_ms,

            "latency_stage2_ms":
                stage2_ms,
        }

    # ============================================================
    # Public interface
    # ============================================================

    def observe(
        self,
        record,
        task_cluster=None,
    ):

        t_total = (
            time.perf_counter_ns()
        )

        gestures = list(
            record.get(
                "gestures",
                [],
            )
        )

        g = len(
            gestures
        )

        # --------------------------------------------------------
        # Warmup
        # --------------------------------------------------------

        if g < START_G:

            return {
                "runtime_version":
                    self.VERSION,

                "gesture":
                    g,

                "phase":
                    "WARMUP",

                "response":
                    "MONITOR",

                "reason":
                    "INSUFFICIENT_PREFIX",

                "strict_score":
                    None,

                "evidence_region":
                    None,

                "tau_low":
                    self.tau_low,

                "tau_high":
                    self.tau_high,

                "cf_checked":
                    False,

                "latency_total_ms":
                    (
                        time.perf_counter_ns()
                        -
                        t_total
                    )
                    /
                    1e6,
            }

        # --------------------------------------------------------
        # Current calibrated deployment horizon
        # --------------------------------------------------------

        if g > STOP_G:

            return {
                "runtime_version":
                    self.VERSION,

                "gesture":
                    g,

                "phase":
                    "OUT_OF_WINDOW",

                "response":
                    "MONITOR",

                "reason":
                    "OUTSIDE_CALIBRATED_WINDOW",

                "strict_score":
                    None,

                "evidence_region":
                    None,

                "tau_low":
                    self.tau_low,

                "tau_high":
                    self.tau_high,

                "cf_checked":
                    False,

                "latency_total_ms":
                    (
                        time.perf_counter_ns()
                        -
                        t_total
                    )
                    /
                    1e6,
            }

        # --------------------------------------------------------
        # Layer 1: Behavioral evidence
        # --------------------------------------------------------

        t0 = time.perf_counter_ns()

        strict_score = (
            self._strict_score(
                record,
                gestures,
            )
        )

        strict_ms = (
            time.perf_counter_ns()
            -
            t0
        ) / 1e6

        region = (
            self._region(
                strict_score
            )
        )

        # --------------------------------------------------------
        # HIGH:
        # Human-calibrated high-confidence evidence.
        # No need to spend more latency.
        # --------------------------------------------------------

        if region == "HIGH":

            return {
                "runtime_version":
                    self.VERSION,

                "gesture":
                    g,

                "phase":
                    "ACTIVE",

                "response":
                    "INTERVENE",

                "reason":
                    "HIGH_CALIBRATED_EVIDENCE",

                "strict_score":
                    strict_score,

                "evidence_region":
                    region,

                "tau_low":
                    self.tau_low,

                "tau_high":
                    self.tau_high,

                "v1_detect":
                    None,

                "v2_detect":
                    None,

                "v3_detect":
                    None,

                "legacy_final":
                    None,

                "cf_checked":
                    False,

                "cf_fragile":
                    False,

                "cf_confirmed":
                    False,

                "latency_strict_ms":
                    strict_ms,

                "latency_base_ms":
                    0.0,

                "latency_stage1_ms":
                    0.0,

                "latency_stage2_ms":
                    0.0,

                "latency_total_ms":
                    (
                        time.perf_counter_ns()
                        -
                        t_total
                    )
                    /
                    1e6,
            }

        # --------------------------------------------------------
        # Layer 2: Secondary frozen evidence
        # --------------------------------------------------------

        tb = time.perf_counter_ns()

        base = self._base_evidence(
            record=
                record,

            gestures=
                gestures,

            task_cluster=
                task_cluster,
        )

        base_ms = (
            time.perf_counter_ns()
            -
            tb
        ) / 1e6

        # --------------------------------------------------------
        # UNCERTAIN + legacy positive
        #
        # Do not run negative-side CF:
        # its semantics assume V1-benign base.
        # --------------------------------------------------------

        if (
            region
            ==
            "UNCERTAIN"
            and
            base[
                "legacy_final"
            ]
        ):

            return {
                "runtime_version":
                    self.VERSION,

                "gesture":
                    g,

                "phase":
                    "ACTIVE",

                "response":
                    "ASK_HOLD",

                "reason":
                    "UNCERTAIN_PLUS_LEGACY_EVIDENCE",

                "strict_score":
                    strict_score,

                "evidence_region":
                    region,

                "tau_low":
                    self.tau_low,

                "tau_high":
                    self.tau_high,

                "v1_detect":
                    base["v1"],

                "v2_detect":
                    base["v2"],

                "v3_detect":
                    base["v3"],

                "legacy_final":
                    base[
                        "legacy_final"
                    ],

                "cf_checked":
                    False,

                "cf_fragile":
                    False,

                "cf_confirmed":
                    False,

                "latency_strict_ms":
                    strict_ms,

                "latency_base_ms":
                    base_ms,

                "latency_stage1_ms":
                    0.0,

                "latency_stage2_ms":
                    0.0,

                "latency_total_ms":
                    (
                        time.perf_counter_ns()
                        -
                        t_total
                    )
                    /
                    1e6,
            }

        # --------------------------------------------------------
        # LOW + legacy positive
        #
        # Weak strict evidence conflicts with the old
        # binary composition. Do not hard-block.
        # --------------------------------------------------------

        if (
            region
            ==
            "LOW"
            and
            base[
                "legacy_final"
            ]
        ):

            return {
                "runtime_version":
                    self.VERSION,

                "gesture":
                    g,

                "phase":
                    "ACTIVE",

                "response":
                    "MONITOR",

                "reason":
                    "LOW_STRICT_LEGACY_POSITIVE",

                "strict_score":
                    strict_score,

                "evidence_region":
                    region,

                "tau_low":
                    self.tau_low,

                "tau_high":
                    self.tau_high,

                "v1_detect":
                    base["v1"],

                "v2_detect":
                    base["v2"],

                "v3_detect":
                    base["v3"],

                "legacy_final":
                    base[
                        "legacy_final"
                    ],

                "cf_checked":
                    False,

                "cf_fragile":
                    False,

                "cf_confirmed":
                    False,

                "latency_strict_ms":
                    strict_ms,

                "latency_base_ms":
                    base_ms,

                "latency_stage1_ms":
                    0.0,

                "latency_stage2_ms":
                    0.0,

                "latency_total_ms":
                    (
                        time.perf_counter_ns()
                        -
                        t_total
                    )
                    /
                    1e6,
            }

        # --------------------------------------------------------
        # At this point legacy is benign.
        #
        # Existing negative-side CF semantics are valid.
        # --------------------------------------------------------

        cf = self._cf_stability(
            record=
                record,

            gestures=
                gestures,

            task_cluster=
                task_cluster,
        )

        if cf[
            "confirmed"
        ]:

            response = "ASK_HOLD"

            reason = (
                "CF_CONFIRMED_INSTABILITY"
            )

        elif cf[
            "fragile"
        ]:

            response = "MONITOR"

            reason = (
                "CF_UNCONFIRMED_INSTABILITY"
            )

        elif region == "UNCERTAIN":

            response = "MONITOR"

            reason = (
                "UNCERTAIN_BUT_CF_STABLE"
            )

        else:

            response = "ALLOW"

            reason = (
                "LOW_EVIDENCE_CF_STABLE"
            )

        return {
            "runtime_version":
                self.VERSION,

            "gesture":
                g,

            "phase":
                "ACTIVE",

            "response":
                response,

            "reason":
                reason,

            "strict_score":
                strict_score,

            "evidence_region":
                region,

            "tau_low":
                self.tau_low,

            "tau_high":
                self.tau_high,

            "v1_detect":
                base["v1"],

            "v2_detect":
                base["v2"],

            "v3_detect":
                base["v3"],

            "legacy_final":
                base[
                    "legacy_final"
                ],

            "cf_checked":
                True,

            "cf_fragile":
                cf[
                    "fragile"
                ],

            "cf_confirmed":
                cf[
                    "confirmed"
                ],

            "stage1_flips":
                cf[
                    "stage1_flips"
                ],

            "stage2_flips":
                cf[
                    "stage2_flips"
                ],

            "stage1_positions":
                cf[
                    "stage1_positions"
                ],

            "stage2_positions":
                cf[
                    "stage2_positions"
                ],

            "n_stage1_probes":
                cf[
                    "n_stage1_probes"
                ],

            "n_stage2_probes":
                cf[
                    "n_stage2_probes"
                ],

            "latency_strict_ms":
                strict_ms,

            "latency_base_ms":
                base_ms,

            "latency_stage1_ms":
                cf[
                    "latency_stage1_ms"
                ],

            "latency_stage2_ms":
                cf[
                    "latency_stage2_ms"
                ],

            "latency_total_ms":
                (
                    time.perf_counter_ns()
                    -
                    t_total
                )
                /
                1e6,
        }

    # compatibility alias
    def evaluate_prefix(
        self,
        record,
        task_cluster=None,
    ):

        return self.observe(
            record,
            task_cluster=
                task_cluster,
        )
