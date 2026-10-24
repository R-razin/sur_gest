import numpy as np


def extract(landmarks):
    """Orientation-, translation-, scale- and reflection-invariant static-pose descriptor.

    Uses ratios of intra-hand 3D landmark distances (not absolute xyz). A rotated
    or mirrored hand gives the same features in an ideal landmark coordinate
    system. Does not solve occlusion or a poorly estimated depth coordinate.
    """
    points = np.asarray(landmarks, dtype=float)
    if points.shape != (21, 3) or not np.isfinite(points).all():
        raise ValueError('Expected 21 finite three-dimensional hand landmarks.')
    # Stable palm reference: multiple bones avoid a single degenerate length.
    palm = np.array([np.linalg.norm(points[i] - points[0]) for i in (5, 9, 13, 17)])
    scale = float(np.median(palm))
    if scale < 1e-6:
        raise ValueError('Hand landmarks have no usable scale.')
    # 210 unique 3D pairwise distances; invariant to rigid rotations and mirrors.
    ii, jj = np.triu_indices(21, k=1)
    distances = np.linalg.norm(points[ii] - points[jj], axis=1) / scale
    # Ratios of tip-to-base and tip-to-wrist distances to corresponding finger
    # lengths improve generalization across hand sizes and proportions.
    finger_ratios = []
    for base, tip in ((1, 4), (5, 8), (9, 12), (13, 16), (17, 20)):
        chain = sum(np.linalg.norm(points[j] - points[j - 1]) for j in range(base + 1, tip + 1))
        if chain < 1e-6:
            raise ValueError('Degenerate finger landmarks.')
        finger_ratios.extend((np.linalg.norm(points[tip] - points[base]) / chain,
                              np.linalg.norm(points[tip] - points[0]) / scale))
    return np.concatenate((distances, np.asarray(finger_ratios, dtype=float)))

def finger_posture(landmarks):
    """Conservative finger-shape cue; returns 'fist', 'open', or 'uncertain'.

    Uses four non-thumb fingers and relative lengths, rather than screen angle.
    This is a cross-check for static zoom commands, not universal pose recognition.
    """
    points = np.asarray(landmarks, dtype=float)
    if points.shape != (21, 3) or not np.isfinite(points).all():
        raise ValueError('Expected 21 finite three-dimensional hand landmarks.')
    ratios = []
    for base, tip in ((5, 8), (9, 12), (13, 16), (17, 20)):
        palm = np.linalg.norm(points[base] - points[0])
        if palm < 1e-6:
            return 'uncertain'
        ratios.append(np.linalg.norm(points[tip] - points[base]) / palm)
    # Require agreement among all four fingers; borderline shapes stay uncertain.
    if max(ratios) < 1.05:
        return 'fist'
    if min(ratios) > 1.25:
        return 'open'
    return 'uncertain'

def synthetic(pose: int, seed: int = 0):
    """Synthetic static finger-extension patterns for simulation testing."""
    rng = np.random.default_rng(seed)
    patterns = [
        [1,1,1,1,1],  # 0: Open palm
        [0,0,0,0,0],  # 1: Closed fist
        [0,1,0,0,0],  # 2: Index finger
        [0,1,1,0,0],  # 3: Two fingers (Peace)
        [1,0,0,0,1],  # 4: Thumb & pinky (Shaka)
        [1,0,0,0,0],  # 5: Thumbs up (confirmation symbol)
    ]
    points = [[.5,.83,0]]
    for finger, extended in enumerate(patterns[pose % len(patterns)]):
        x = .29 + finger*.105
        for joint in range(4):
            y = .68 - joint*(.135 if extended else .025)
            points.append([x + (joint*.014 if finger == 0 else 0), y, -.015*joint if extended else .025*joint])
    return (np.array(points)+rng.normal(0,.002,(21,3))).tolist()

class LandmarkSmoother:
    def __init__(self): self.previous = None
    def reset(self): self.previous = None
    def apply(self, points, amount):
        value = np.asarray(points,float)
        extract(value)
        if self.previous is not None:
            # Do not blend distinct hand shapes: blending fist into palm can
            # invent an intermediate pose and postpone or invert recognition.
            old_shape = finger_posture(self.previous)
            new_shape = finger_posture(value)
            if old_shape == new_shape or 'uncertain' in (old_shape, new_shape):
                value = amount*self.previous+(1-amount)*value
        self.previous=value
        return value.tolist()
