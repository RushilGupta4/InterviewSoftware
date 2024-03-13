import json
from deepface import DeepFace

backend_opts = ["opencv", "retinaface", "mtcnn", "ssd", "mediapipe", "yolov8"]

data = {}

imgs = [
    "img/img1.jpg",
    "img/img2.jpg",
    "img/img3.jpg",
    "img/img4.jpg",
    "img/img5.JPG",
    "img/img6.JPG",
    "img/img7.JPG",
    "img/img8.JPG",
]

for i in imgs:
    data[i] = {}
    for b in backend_opts:
        data[i][b] = DeepFace.analyze(
            img_path=i, actions=["emotion"], detector_backend=b, enforce_detection=False
        )

with open("data.json", "w") as f:
    json.dump(data, f, indent=2)
