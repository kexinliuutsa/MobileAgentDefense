import json
from pathlib import Path
import numpy as np
from sklearn.base import BaseEstimator
from sklearn.preprocessing import RobustScaler
from sklearn.neighbors import NearestNeighbors

ROOT = Path(__file__).resolve().parents[2]
def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
def threshold(scores, y, target=0.025):
    human = np.sort(np.asarray(scores)[np.asarray(y) == 0])[::-1]
    if not len(human):
        raise ValueError("Human validation samples required")
    allowed = int(np.floor(target * len(human)))
    return float(np.nextafter(human[allowed], np.inf))

class HumanReference(BaseEstimator):
    """Human-only robust scaling and mean five-neighbor distance, human ECDF score."""
    def fit(self, X, y):
        h = np.asarray(X)[np.asarray(y) == 0]
        self.scaler = RobustScaler().fit(h)
        z = self.scaler.transform(h)
        self.k = min(5, len(h)-1)
        if self.k < 1: raise ValueError("At least two training humans required")
        self.nn = NearestNeighbors(n_neighbors=self.k).fit(z)
        self.reference = np.sort(self.nn.kneighbors(z, n_neighbors=self.k+1)[0][:,1:].mean(axis=1))
        return self
    def score(self, X):
        distances = self.nn.kneighbors(self.scaler.transform(X))[0].mean(axis=1)
        return np.searchsorted(self.reference, distances, side="right") / len(self.reference)

class FakeRules:
    """Upper action-count tail plus two-sided duration/gap/displacement tails."""
    def fit(self, X, y, columns):
        self.columns = [c for c in columns if c == "n_actions" or
                        (c.startswith("session_") and any(s in c for s in ("duration", "gap", "displacement")))]
        h = X.loc[np.asarray(y)==0, self.columns].to_numpy(float)
        self.low = np.quantile(h, .01, axis=0)
        self.high = np.quantile(h, .99, axis=0)
        self.scale = np.maximum(np.quantile(h,.75,axis=0)-np.quantile(h,.25,axis=0), .001)
        return self
    def score(self, X):
        z = X[self.columns].to_numpy(float)
        excess = np.maximum((z-self.high)/self.scale, (self.low-z)/self.scale)
        if "n_actions" in self.columns:
            j=self.columns.index("n_actions"); excess[:,j]=(z[:,j]-self.high[j])/self.scale[j]
        return 1-np.exp(-np.maximum(excess,0).max(axis=1))
    def export(self):
        return {"columns":self.columns,"low":self.low.tolist(),"high":self.high.tolist(),"scale":self.scale.tolist(),"rule":"maximum human-training tail excess; upper-tail only for n_actions"}
    @classmethod
    def load(cls, d):
        r=cls(); r.columns=d["columns"]
        for k in ("low","high","scale"): setattr(r,k,np.array(d[k]))
        return r

def head_scores(bundle, X, schema):
    return np.column_stack([bundle["session"].predict_proba(X[schema["session_54d"]])[:,1],
        bundle["strict"].predict_proba(X[schema["strict_cross_17d"]])[:,1],
        bundle["human"].score(X[schema["session_54d"]+schema["strict_cross_17d"]].to_numpy(float)),
        bundle["fake"].score(X), X["n_actions"].to_numpy(float)])
def scores(bundle, X, schema):
    h=head_scores(bundle,X,schema)
    return {"session only":h[:,0],"strict only":h[:,1],"human-reference only":h[:,2],
        "fake only":h[:,3],"session + strict":bundle["pair"].predict_proba(h[:,:2])[:,1],
        "full fusion":bundle["fusion"].predict_proba(h)[:,1]}
