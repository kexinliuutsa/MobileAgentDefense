"""Repair only the author threshold-posterior helper used by UltimateClassifier.predict().

Source lineage: P19_source_bundle.zip / LEGACY/m4z3_direct_ultimate_predict.py,
corrected_smoothed_logodds (historical experimental implementation).
This module does NOT replace UltimateClassifier.predict(), refit a threshold,
or implement a score surrogate. It must be used with the actual AHB model assets.
"""
import math
from contextlib import contextmanager

ALPHA = 0.5

def corrected_smoothed_logodds(value, threshold_info):
    m = threshold_info.metrics
    tp, fp, tn, fn = (float(m.TP), float(m.FP), float(m.TN), float(m.FN))
    tpr = (tp + ALPHA) / (tp + fn + 2.0 * ALPHA)
    fpr = (fp + ALPHA) / (fp + tn + 2.0 * ALPHA)
    low_logodds = math.log((1.0 - tpr) / (1.0 - fpr))
    high_logodds = math.log(tpr / fpr)
    if float(value) < float(threshold_info.threshold):
        return float(low_logodds)
    return float(high_logodds)

@contextmanager
def patched_author_helper():
    """Within this context UltimateClassifier.predict executes unmodified."""
    from analysis.processing import judge_library
    original = judge_library.get_log_odds_with_threshold_posterior
    judge_library.get_log_odds_with_threshold_posterior = corrected_smoothed_logodds
    try:
        yield judge_library.UltimateClassifier
    finally:
        judge_library.get_log_odds_with_threshold_posterior = original
