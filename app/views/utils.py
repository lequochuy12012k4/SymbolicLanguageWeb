import os
import urllib.request
import traceback
import tempfile
import numpy as np
import cv2
import mediapipe as mp
import tensorflow as tf
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from django.core.cache import cache
from app.models import AIModel

# 2. MediaPipe Holistic Landmarker Model
MODEL_MP_PATH = 'holistic_landmarker.task'

def get_active_ai_model():
    """Gets the active AI model from the cache or database."""
    active_model = cache.get('active_ai_model')
    if not active_model:
        try:
            active_model_instance = AIModel.objects.get(is_active=True)
            active_model = tf.keras.models.load_model(active_model_instance.file_path)
            cache.set('active_ai_model', active_model, timeout=3600) # Cache for 1 hour
            print(f"INFO: Tải và cache mô hình hoạt động: {active_model_instance.name}")
        except AIModel.DoesNotExist:
            print("LỖI NGHIÊM TRỌNG: Không tìm thấy mô hình AI nào được kích hoạt.")
            return None
        except Exception as e:
            print(f"LỖI NGHIÊM TRỌNG: Không thể tải mô hình từ đường dẫn được chỉ định.")
            print(f"Chi tiết lỗi: {e}")
            return None
    return active_model

# Download the model file at startup if it doesn't exist.
if not os.path.exists(MODEL_MP_PATH):
    print(f"INFO: Mô hình MediaPipe không tồn tại. Đang tải xuống '{MODEL_MP_PATH}'...")
    try:
        url = 'https://storage.googleapis.com/mediapipe-models/holistic_landmarker/holistic_landmarker/float16/latest/holistic_landmarker.task'
        urllib.request.urlretrieve(url, MODEL_MP_PATH)
        print("INFO: Tải xuống mô hình MediaPipe hoàn tất.")
    except Exception as e:
        print(f"LỖI NGHIÊM TRỌNG KHI KHỞI ĐỘNG: Không thể tải xuống mô hình MediaPipe.")
        print(f"Chi tiết lỗi: {e}")
        traceback.print_exc()

CLASS_NAMES = [
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
    'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
    'Ba', 'Mẹ', 'Gia đình', 'Trường học'
]

def extract_keypoints_from_result(detection_result):
    lh = np.zeros(21 * 3)
    if detection_result.left_hand_landmarks:
        lh = np.array([[res.x, res.y, res.z] for res in detection_result.left_hand_landmarks]).flatten()

    rh = np.zeros(21 * 3)
    if detection_result.right_hand_landmarks:
        rh = np.array([[res.x, res.y, res.z] for res in detection_result.right_hand_landmarks]).flatten()

    pose = np.zeros(4 * 3)
    if detection_result.pose_landmarks:
        landmarks = detection_result.pose_landmarks
        if len(landmarks) > 14:
            pose_subset = [landmarks[11], landmarks[12], landmarks[13], landmarks[14]]
            pose = np.array([[res.x, res.y, res.z] for res in pose_subset]).flatten()
    
    return np.concatenate([lh, rh, pose])

def predict_from_video_file(video_file):
    model_tf = get_active_ai_model()

    if not model_tf or not os.path.exists(MODEL_MP_PATH):
        return None, "Mô hình dự đoán hoặc MediaPipe không khả dụng."

    temp_video_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_f:
            temp_video_path = temp_f.name
            for chunk in video_file.chunks():
                temp_f.write(chunk)

        BaseOptions = python.BaseOptions
        HolisticLandmarker = vision.HolisticLandmarker
        HolisticLandmarkerOptions = vision.HolisticLandmarkerOptions
        VisionRunningMode = vision.RunningMode

        options = HolisticLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_MP_PATH),
            running_mode=VisionRunningMode.VIDEO
        )

        with HolisticLandmarker.create_from_options(options) as landmarker:
            sequence = []
            cap = cv2.VideoCapture(temp_video_path)
            frame_count = 0
            while cap.isOpened() and frame_count < 30:
                ret, frame = cap.read()
                if not ret:
                    break

                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                timestamp = int(cap.get(cv2.CAP_PROP_POS_MSEC))
                detection_result = landmarker.detect_for_video(mp_image, timestamp)
                
                keypoints = extract_keypoints_from_result(detection_result)
                sequence.append(keypoints)
                frame_count += 1
            cap.release()

            while len(sequence) < 30:
                sequence.append(np.zeros(138))

            input_data = np.expand_dims(np.array(sequence), axis=0)
            prediction = model_tf.predict(input_data)[0]
            predicted_class_index = np.argmax(prediction)
            final_prediction_name = CLASS_NAMES[predicted_class_index]
            
            return final_prediction_name, None

    except Exception as e:
        traceback.print_exc()
        return None, f"Đã xảy ra lỗi: {e}"
    finally:
        if temp_video_path and os.path.exists(temp_video_path):
            os.unlink(temp_video_path)
