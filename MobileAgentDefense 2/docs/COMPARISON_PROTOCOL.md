# Author vs ours: paired native comparison requirements

The validated experiment uses repaired official `UltimateClassifier.predict()` versus the frozen packaged V3 defense. Compare attack detection accuracy and early detection speed at each method's original operating point (no FPR matching, no new thresholds). Pair by the same underlying sessions and preserve coverage and human-session denominator.

Historical reported checkpoints: Long-Tap final 157/169 author vs 169/169 ours; early g11 157/169 vs 168/169. These are **previously reported evidence**, not tests rerun by this ZIP, and do not prove cross-device generality.

Do not claim end-to-end reproducibility until the original local `.pkl`, `.joblib`, underlying records and frozen online code are restored. No user data, private logs, or API credentials should be packaged automatically.
