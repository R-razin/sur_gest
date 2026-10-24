from threading import Lock
import base64
import os
import numpy as np

class Camera:
    def __init__(self):
        self.detector=None
        self.lock=Lock()
    def detect(self,encoded):
        with self.lock:
            return self._detect(encoded)

    def _detect(self,encoded):
        path=os.getenv('AIRCONTROL_MODEL','models/hand_landmarker.task')
        if not os.path.isfile(path):
            raise RuntimeError('Hand Landmarker model is missing. Run scripts/download-model.ps1, then retry. Simulation remains available.')
        import cv2
        import mediapipe as mp
        try: raw=base64.b64decode(encoded.split(',')[-1],validate=True)
        except Exception as exc: raise ValueError('Invalid camera image encoding.') from exc
        data=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        if data is None or max(data.shape[:2])>1920: raise ValueError('Invalid image or image exceeds 1920 pixels.')
        if self.detector is None:
            options=mp.tasks.vision.HandLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=path),num_hands=1)
            self.detector=mp.tasks.vision.HandLandmarker.create_from_options(options)
        result=self.detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(data,cv2.COLOR_BGR2RGB)))
        return [[p.x,p.y,p.z] for p in result.hand_landmarks[0]] if result.hand_landmarks else None
