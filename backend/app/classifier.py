import numpy as np
from sklearn.neighbors import KNeighborsClassifier
from .features import extract


class PersonalizedClassifier:
    """
    Personalized static-pose classifier.

    Confidence combines the KNN vote with distance from the enrolled examples.
    The distance scale is estimated from the user's own training samples instead
    of using one overly strict fixed radius for every camera/user.
    """

    def __init__(self):
        self.model = None
        self.radius = 0.35
        self.labels = set()
        self.radii = {}
        self.class_samples = {}

    def train(self, rows):
        if not rows:
            self.model = None
            self.labels = set()
            self.radius = 0.35
            self.radii = {}
            self.class_samples = {}
            return

        x = np.asarray([extract(r["landmarks"]) for r in rows], dtype=float)
        y = [r["label"] for r in rows]

        self.model = KNeighborsClassifier(
            n_neighbors=min(3, len(x)),
            weights="distance",
        ).fit(x, y)
        self.labels = set(y)

        # Estimate a useful distance scale from the enrolled samples.
        # Each sample is compared with its nearest *other* sample. This avoids
        # the zero distance each point would have to itself.
        self.radii = {}
        self.class_samples = {}
        for label in self.labels:
            same = x[np.asarray(y) == label]
            self.class_samples[label] = same
            pairwise = np.linalg.norm(same[:, None] - same[None, :], axis=2)
            np.fill_diagonal(pairwise, np.inf)
            nearest_other = pairwise.min(axis=1)
            positive = nearest_other[np.isfinite(nearest_other) & (nearest_other > 1e-8)]
            radius = .35
            if positive.size:
                # Use a robust upper-typical distance, then add headroom for
                # natural pose variation during a fresh verification capture.
                learned_radius = float(np.percentile(positive, 90) * 2.5)
                radius = max(0.35, min(2.0, learned_radius))
            self.radii[label] = radius
        self.radius = max(self.radii.values(), default=.35)

    def predict(self, points, sensitivity=1):
        if self.model is None:
            raise ValueError(
                "Enroll at least one gesture with eight examples before recognition."
            )

        feature = extract(points).reshape(1, -1)
        distances, _ = self.model.kneighbors(feature, n_neighbors=1)
        probabilities = self.model.predict_proba(feature)[0]
        index = int(np.argmax(probabilities))
        predicted = str(self.model.classes_[index])
        nearest_distance = float(np.min(np.linalg.norm(self.class_samples[predicted]-feature, axis=1)))

        # Sensitivity scales the rejection radius but does not bypass the
        # confidence threshold or the app's independent verification stages.
        effective_radius = max(0.05, self.radii[predicted] * max(0.25, float(sensitivity)))
        confidence = float(
            probabilities[index]
            * np.exp(-0.5 * (nearest_distance / effective_radius) ** 2)
        )
        confidence = float(np.clip(confidence, 0.0, 1.0))
        return str(self.model.classes_[index]), confidence
