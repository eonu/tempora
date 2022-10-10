from __future__ import annotations

from typing import Optional, Any

from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.metrics import accuracy_score, r2_score

from sequentia.utils.validation import Array
from sequentia.utils.decorators import _requires_fit

class _Classifier(BaseEstimator, ClassifierMixin):
    def fit(
        self,
        X: Array,
        y: Array[int],
        lengths: Optional[Array[int]] = None
    ) -> _Classifier:
        raise NotImplementedError

    def predict(
        self,
        X: Array,
        lengths: Optional[Array[int]] = None
    ) -> Array[int]:
        """TODO"""

        raise NotImplementedError

    def predict_proba(
        self,
        X: Array,
        lengths: Optional[Array[int]] = None
    ) -> Array[float]:
        """TODO"""

        raise NotImplementedError

    def predict_scores(
        self,
        X: Array,
        lengths: Optional[Array[int]] = None
    ) -> Array[float]:
        """TODO"""

        raise NotImplementedError

    @_requires_fit
    def score(
        self,
        X: Array,
        y: Array[int],
        lengths: Optional[Array[int]] = None,
        sample_weight: Optional[Any] = None
    ) -> float:
        """TODO"""

        y_pred = self.predict(X, lengths)
        return accuracy_score(y, y_pred, sample_weight=sample_weight)

class _Regressor(BaseEstimator, RegressorMixin):
    def fit(
        self,
        X: Array[float],
        y: Array[float],
        lengths: Optional[Array[int]] = None
    ) -> _Regressor:
        """TODO"""

        raise NotImplementedError

    def predict(
        self,
        X: Array[float],
        lengths: Optional[Array[int]] = None
    ) -> Array[float]:
        """TODO"""

        raise NotImplementedError

    @_requires_fit
    def score(
        self,
        X: Array[float],
        y: Array[float],
        lengths: Optional[Array[int]] = None,
        sample_weight: Optional[Any] = None
    ) -> float:
        """TODO"""

        y_pred = self.predict(X, lengths)
        return r2_score(y, y_pred, sample_weight=sample_weight)
