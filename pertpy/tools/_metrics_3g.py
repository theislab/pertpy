from collections.abc import Mapping
from functools import partial
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Optional

import anndata as ad
import numpy as np
import pandas as pd
import pynndescent
import scanpy as sc
from scipy.sparse import issparse
from scipy.sparse import vstack as sp_vstack
from sklearn.base import ClassifierMixin
from sklearn.linear_model import LogisticRegression

from pertpy.tools._distances._distances import Distance

if TYPE_CHECKING:
    from numpy.typing import NDArray


def compare_de(X: np.ndarray, Y: np.ndarray, C: np.ndarray, shared_top: int = 100, **kwargs) -> dict:
    """Compare DEG across real and simulated perturbations.

    Computes DEG for real and simulated perturbations vs. control and calculates
    metrics to evaluate similarity of the results.

    Args:
        X: Real perturbed data.
        Y: Simulated perturbed data.
        C: Control data
        shared_top: The number of top DEG to compute the proportion of their intersection.
        **kwargs: arguments for `scanpy.tl.rank_genes_groups`.
    """
    n_vars = X.shape[1]
    assert n_vars == Y.shape[1] == C.shape[1]

    shared_top = min(shared_top, n_vars)
    vars_ranks = np.arange(1, n_vars + 1)

    adatas_xy = {}
    adatas_xy["x"] = ad.AnnData(X, obs={"label": "comp"})
    adatas_xy["y"] = ad.AnnData(Y, obs={"label": "comp"})
    adata_c = ad.AnnData(C, obs={"label": "ctrl"})

    results = pd.DataFrame(index=adata_c.var_names)
    top_names = []
    for group in ("x", "y"):
        adata_joint = ad.concat((adatas_xy[group], adata_c), index_unique="-")

        sc.tl.rank_genes_groups(adata_joint, groupby="label", reference="ctrl", key_added="de", **kwargs)

        srt_idx = np.argsort(adata_joint.uns["de"]["names"]["comp"])
        results[f"scores_{group}"] = adata_joint.uns["de"]["scores"]["comp"][srt_idx]
        results[f"pvals_adj_{group}"] = adata_joint.uns["de"]["pvals_adj"]["comp"][srt_idx]
        results[f"ranks_{group}"] = vars_ranks[srt_idx]

        top_names.append(adata_joint.uns["de"]["names"]["comp"][:shared_top])

    metrics = {}
    metrics["shared_top_genes"] = len(set(top_names[0]).intersection(top_names[1])) / shared_top
    metrics["scores_corr"] = results["scores_x"].corr(results["scores_y"], method="pearson")
    metrics["pvals_adj_corr"] = results["pvals_adj_x"].corr(results["pvals_adj_y"], method="pearson")
    metrics["scores_ranks_corr"] = results["ranks_x"].corr(results["ranks_y"], method="spearman")

    return metrics


def compare_class(X: np.ndarray, Y: np.ndarray, C: np.ndarray, clf: ClassifierMixin | None = None) -> float:
    """Compare classification accuracy between real and simulated perturbations.

    Trains a classifier on the real perturbation data + the control data and reports a normalized
    classification accuracy on the simulated perturbation.

    Args:
        X: Real perturbed data.
        Y: Simulated perturbed data.
        C: Control data
        clf: sklearn classifier to use, `sklearn.linear_model.LogisticRegression` if not provided.
    """
    assert X.shape[1] == Y.shape[1] == C.shape[1]

    if clf is None:
        clf = LogisticRegression()

    n_x = X.shape[0]
    n_xc = n_x + C.shape[0]

    data = sp_vstack((X, C)) if issparse(X) else np.vstack((X, C))

    labels = np.full(n_xc, "ctrl")
    labels[:n_x] = "comp"
    clf.fit(data, labels)

    norm_score = clf.score(Y, np.full(Y.shape[0], "comp")) / clf.score(X, labels[:n_x])
    norm_score = min(1.0, norm_score)

    return norm_score


def compare_knn(
    X: np.ndarray,
    Y: np.ndarray,
    C: np.ndarray | None = None,
    n_neighbors: int = 20,
    use_Y_knn: bool = False,
    random_state: int = 0,
    n_jobs: int = 1,
) -> dict[str, float]:
    """Calculate proportions of real perturbed and control data points for simulated data.

    Computes proportions of real perturbed (if provided), control and simulated (if `use_Y_knn=True`)
    data points for simulated data. If control (`C`) is not provided, builds the knn graph from
    real perturbed + simulated perturbed.

    Args:
        X: Real perturbed data.
        Y: Simulated perturbed data.
        C: Control data.
        use_Y_knn: Include simulted perturbed data (`Y`) into the knn graph. Only valid when
            control (`C`) is provided.
    """
    assert X.shape[1] == Y.shape[1]
    if C is not None:
        assert X.shape[1] == C.shape[1]

    n_y = Y.shape[0]

    if C is None:
        index_data = sp_vstack((Y, X)) if issparse(X) else np.vstack((Y, X))
    else:
        datas = (Y, X, C) if use_Y_knn else (X, C)
        index_data = sp_vstack(datas) if issparse(X) else np.vstack(datas)

    y_in_index = use_Y_knn or C is None
    c_in_index = C is not None
    label_groups = ["comp"]
    labels: NDArray[np.str_] = np.full(index_data.shape[0], "comp")
    if y_in_index:
        labels[:n_y] = "siml"
        label_groups.append("siml")
    if c_in_index:
        labels[-C.shape[0] :] = "ctrl"
        label_groups.append("ctrl")

    index = pynndescent.NNDescent(
        index_data,
        n_neighbors=max(50, n_neighbors),
        random_state=random_state,
        n_jobs=n_jobs,
    )
    indices = index.query(Y, k=n_neighbors)[0]

    uq, uq_counts = np.unique(labels[indices], return_counts=True)
    uq_counts_norm = uq_counts / uq_counts.sum()
    counts = dict(zip(label_groups, [0.0] * len(label_groups), strict=False))
    for group, count_norm in zip(uq, uq_counts_norm, strict=False):
        counts[group] = count_norm

    return counts


def compare_dist(
    pert: np.ndarray,
    pred: np.ndarray,
    ctrl: np.ndarray,
    *,
    metric: str = "euclidean",
    mode: Literal["simple", "scaled"] = "simple",
    metric_kwds: Mapping[str, Any] = MappingProxyType({}),
    _fit_to_pert_and_ctrl: bool = False,
) -> float:
    """Compute the score of simulating a perturbation.

    Args:
        pert: Real perturbed data.
        pred: Simulated perturbed data.
        ctrl: Control data
        mode: Mode to use.
    """
    metric_fct = partial(Distance(metric).metric_fct, **metric_kwds)

    if mode == "simple":
        pass  # nothing to be done
    elif mode == "scaled":
        from sklearn.preprocessing import MinMaxScaler

        scaler = MinMaxScaler().fit(np.vstack((pert, ctrl)) if _fit_to_pert_and_ctrl else ctrl)
        pred = scaler.transform(pred)
        pert = scaler.transform(pert)
    else:
        raise ValueError(f"Unknown mode {mode}. Please choose simple or scaled.")

    d1 = metric_fct(pert, pred)
    d2 = metric_fct(ctrl, pred)
    return d1 / d2