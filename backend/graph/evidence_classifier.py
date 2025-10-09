"""Simple logistic-regression classifier for evidence quality signals.

The heuristics in :mod:`backend.graph.evidence_quality` provide weighted
scores that work well for ranking but the blueprint calls for a learned
signal that can tag edges as *high* or *low* confidence based on richer
metadata.  We keep the implementation intentionally lightweight by using
NumPy-backed gradient descent instead of introducing a heavy dependency on
scikit-learn.  This keeps the optional ``text-mining`` extra focused on
spaCy/scispaCy upgrades while still unlocking a trainable reliability model.

The classifier expects feature dictionaries describing an edge; each feature
vector is converted into a deterministic ordering so training and inference do
not depend on insertion order.  The exported API mirrors scikit-learn's
``fit``/``predict_proba`` interface which lets downstream callers swap in a
different model if needed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np


FeatureVector = Mapping[str, float]


@dataclass(slots=True)
class EvidenceQualityTrainingExample:
    """Training record consumed by :class:`EvidenceQualityClassifier`."""

    features: FeatureVector
    label: int  # 1 = high confidence, 0 = low confidence
    weight: float = 1.0


class EvidenceQualityClassifier:
    """Minimal logistic regression implemented with NumPy."""

    def __init__(self, *, learning_rate: float = 0.2, epochs: int = 200, l2: float = 0.01) -> None:
        self.learning_rate = float(max(1e-4, learning_rate))
        self.epochs = max(10, int(epochs))
        self.l2 = float(max(0.0, l2))
        self._weights: np.ndarray | None = None
        self._bias: float = 0.0
        self._feature_index: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Training & inference API
    # ------------------------------------------------------------------
    def fit(self, samples: Sequence[EvidenceQualityTrainingExample]) -> None:
        if not samples:
            raise ValueError("At least one training example is required")
        self._feature_index = self._build_feature_index(samples)
        matrix, labels, weights = self._encode_samples(samples)
        weight_vector = np.zeros(matrix.shape[1], dtype=float)
        bias = 0.0

        for _ in range(self.epochs):
            logits = matrix @ weight_vector + bias
            predictions = 1.0 / (1.0 + np.exp(-logits))
            errors = predictions - labels
            gradient = (matrix.T @ (errors * weights)) / np.sum(weights)
            if self.l2:
                gradient += self.l2 * weight_vector
            bias_gradient = float(np.sum(errors * weights) / np.sum(weights))
            weight_vector -= self.learning_rate * gradient
            bias -= self.learning_rate * bias_gradient

        self._weights = weight_vector
        self._bias = float(bias)

    def predict_proba(self, features: FeatureVector) -> float:
        if self._weights is None:
            raise RuntimeError("Classifier has not been trained")
        vector = self._encode_feature_vector(features)
        logit = float(self._weights @ vector + self._bias)
        return 1.0 / (1.0 + math.exp(-logit))

    def predict_label(self, features: FeatureVector, threshold: float = 0.5) -> Tuple[str, float]:
        probability = self.predict_proba(features)
        label = "high" if probability >= threshold else "low"
        return label, probability

    # ------------------------------------------------------------------
    # Encoding helpers
    # ------------------------------------------------------------------
    def _encode_samples(
        self, samples: Sequence[EvidenceQualityTrainingExample]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        matrix = np.vstack([self._encode_feature_vector(sample.features) for sample in samples])
        labels = np.asarray([sample.label for sample in samples], dtype=float)
        weights = np.asarray([float(max(sample.weight, 1e-3)) for sample in samples], dtype=float)
        return matrix, labels, weights

    def _encode_feature_vector(self, features: FeatureVector) -> np.ndarray:
        vector = np.zeros(len(self._feature_index), dtype=float)
        for name, index in self._feature_index.items():
            value = float(features.get(name, 0.0))
            vector[index] = value
        return vector

    @staticmethod
    def _build_feature_index(samples: Sequence[EvidenceQualityTrainingExample]) -> Dict[str, int]:
        feature_names: Dict[str, int] = {}
        for sample in samples:
            for name in sample.features.keys():
                if name not in feature_names:
                    feature_names[name] = len(feature_names)
        if not feature_names:
            raise ValueError("No features supplied for training")
        return feature_names


def build_training_examples(
    features: Iterable[FeatureVector],
    labels: Iterable[int],
    *,
    weights: Iterable[float] | None = None,
) -> Sequence[EvidenceQualityTrainingExample]:
    """Utility for zipping feature dictionaries, labels and optional weights."""

    label_list = list(labels)
    feature_list = list(features)
    if len(feature_list) != len(label_list):
        raise ValueError("Feature and label lengths do not match")
    weight_list = list(weights) if weights is not None else [1.0] * len(feature_list)
    if len(weight_list) != len(feature_list):
        raise ValueError("Weight length does not match feature length")
    return [
        EvidenceQualityTrainingExample(features=feature_list[i], label=int(label_list[i]), weight=float(weight_list[i]))
        for i in range(len(feature_list))
    ]


__all__ = [
    "EvidenceQualityClassifier",
    "EvidenceQualityTrainingExample",
    "build_training_examples",
]

