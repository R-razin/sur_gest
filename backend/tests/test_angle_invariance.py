
import numpy as np
import pytest
from app.features import extract, synthetic
from app.classifier import PersonalizedClassifier


def rotate(points, degrees):
    a = np.deg2rad(degrees)
    rz = np.array([[np.cos(a), -np.sin(a), 0],
                   [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    ry = np.array([[np.cos(a), 0, np.sin(a)],
                   [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    return (np.asarray(points) @ (rz @ ry).T).tolist()

@pytest.mark.parametrize('angle', [-150, -90, -45, 0, 45, 90, 150])
def test_rotation_translation_scale_and_mirror(angle):
    base = np.array(synthetic(1, 13))
    rotated = np.array(rotate(base, angle)) * 1.8 + [4, -3, 1]
    assert np.allclose(extract(base), extract(rotated), atol=1e-9)
    rotated[:, 0] *= -1
    assert np.allclose(extract(base), extract(rotated), atol=1e-9)

@pytest.mark.parametrize('pose', list(range(5)))
def test_all_synthetic_gestures_rotate_and_mirror(pose):
    model = PersonalizedClassifier()
    model.train([{'label': str(p), 'landmarks': synthetic(p, seed)}
                 for p in range(5) for seed in range(12)])
    for angle in [-90, 30, 120]:
        points = np.array(rotate(synthetic(pose, 999), angle))
        points[:, 0] *= -1
        label, confidence = model.predict(points.tolist())
        assert label == str(pose)
        assert confidence > 0.1
