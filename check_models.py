import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import cv2
import onnxruntime as ort

models = [
    "models/face_detection_yunet_2023mar.onnx",
    "models/face_recognition_sface_2021dec.onnx",
    "models/minifasnet_v2.onnx",
]

print("OpenCV:", cv2.__version__)
print("ONNX Runtime:", ort.__version__)
print("Available Providers:", ort.get_available_providers())

for model in models:
    if not os.path.exists(model):
        print(f"\nModel {model} NOT FOUND!")
        continue
    session = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
    print("\nModel:", model)
    print("Input:", session.get_inputs()[0].name, session.get_inputs()[0].shape)
    print("Output:", session.get_outputs()[0].name, session.get_outputs()[0].shape)
