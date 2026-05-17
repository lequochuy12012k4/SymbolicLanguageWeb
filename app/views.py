from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import (
    SymbolicLanguage, UserProfile, Course, CourseEnrollment, CourseReview, Post, 
    Comment, Like, AIModel, Chapter, Exercise, Answer, UserExerciseCompletion, 
    SymbolCategory, Symbol, Conversation, Message, AIProvider, APIModel
)
from django.db.models import Count, Q, Exists, OuterRef, Subquery, Max
from django.views.decorators.http import require_POST, require_http_methods
import json
from .forms import (
    UserUpdateForm, ProfileUpdateForm, CustomPasswordChangeForm, PostForm, CommentForm, 
    SymbolCategoryForm, SymbolForm
)
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.urls import reverse
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db.models.functions import TruncMonth

# --- New Imports for Email Activation and Password Reset ---
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import PasswordResetForm
from django.http import HttpResponse

# --- Model Prediction Imports ---
import tensorflow as tf
import numpy as np
import cv2 # OpenCV for video processing
import tempfile
import os
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request
import traceback

# --- Gemini AI Import ---
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.api_core import exceptions as google_exceptions


# --- Model and Landmarker Configuration ---

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


# 2. MediaPipe Holistic Landmarker Model
MODEL_MP_PATH = 'holistic_landmarker.task'

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

if os.path.exists(MODEL_MP_PATH):
    print(f"INFO: Tệp mô hình MediaPipe '{MODEL_MP_PATH}' đã sẵn sàng.")
else:
    print(f"LỖI NGHIÊM TRỌNG KHI KHỞI ĐỘNG: Tệp mô hình MediaPipe '{MODEL_MP_PATH}' không tìm thấy.")


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

@csrf_exempt
def predict_symbol(request):
    if request.method != 'POST':
        return render(request, 'symbols/predict_symbol.html')
        
    video_file = request.FILES.get('video')
    if not video_file:
        return JsonResponse({'error': 'Không tìm thấy tệp video.'}, status=400)

    prediction, error = predict_from_video_file(video_file)

    if error:
        return JsonResponse({'error': error}, status=500)

    return JsonResponse({'prediction': f"Ký hiệu: {prediction}"})

def home(request):
    """Home page view with featured courses"""
    courses = Course.objects.all().order_by('-created_at')
    enrolled_ids = []
    if request.user.is_authenticated:
        enrolled_ids = CourseEnrollment.objects.filter(user_profile__user=request.user).values_list('course_id', flat=True)
    
    context = {
        'courses': courses,
        'enrolled_ids': enrolled_ids
    }
    return render(request, 'pages/home.html', context)

def register(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        if password != password2:
            messages.error(request, 'Mật khẩu không khớp!')
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Tên người dùng đã tồn tại!')
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email đã được sử dụng!')
            return redirect('register')

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_active = False
        # user.save() is not needed here because create_user already saves.
        # Calling it again triggers the post_save signal twice, causing the error.

        # Send activation email
        mail_subject = 'Kích hoạt tài khoản Ngôn Ngữ Ký Hiệu của bạn.'
        message = render_to_string('auth/account_activation_email.html', {
            'user': user,
            'domain': request.get_host(),
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': default_token_generator.make_token(user),
            'protocol': 'https' if request.is_secure() else 'http',
        })
        to_email = email
        send_mail(mail_subject, message, settings.DEFAULT_FROM_EMAIL, [to_email])

        messages.success(request, 'Đăng ký thành công! Vui lòng kiểm tra email của bạn để kích hoạt tài khoản.')
        return redirect('login')

    return render(request, 'auth/register.html')

def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        
        # Automatically enroll the user in the latest course
        try:
            latest_course = Course.objects.latest('created_at')
            user_profile = UserProfile.objects.get(user=user)
            CourseEnrollment.objects.create(user_profile=user_profile, course=latest_course)
            messages.success(request, f'Tài khoản của bạn đã được kích hoạt! Bạn đã được ghi danh vào khóa học "{latest_course.title}".')
        except Course.DoesNotExist:
            messages.success(request, 'Tài khoản của bạn đã được kích hoạt!')
        except UserProfile.DoesNotExist:
            messages.warning(request, 'Tài khoản của bạn đã được kích hoạt, nhưng đã có lỗi xảy ra khi tự động ghi danh vào khóa học.')

        # Log the user in properly
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        return redirect('progress')
    else:
        return render(request, 'auth/activation_invalid.html')

def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('dashboard')
        else:
            return redirect('progress')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if not user.is_active:
                messages.error(request, 'Tài khoản này chưa được kích hoạt. Vui lòng kiểm tra email của bạn.')
                return redirect('login')
            login(request, user)
            messages.success(request, f'Chào mừng {user.username}!')
            if user.is_staff or user.userprofile.is_manager:
                return redirect('dashboard')
            else:
                return redirect('progress')
        else:
            messages.error(request, 'Tên người dùng hoặc mật khẩu không chính xác!')
            return redirect('login')
    
    return render(request, 'auth/login.html')

def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            associated_users = User.objects.filter(Q(email=email))
            if associated_users.exists():
                for user in associated_users:
                    subject = "Yêu cầu đặt lại mật khẩu"
                    email_template_name = "auth/password_reset_email.html"
                    context = {
                        "email": user.email,
                        'domain': request.get_host(),
                        'site_name': 'SymbolicLanguageWeb',
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        "user": user,
                        'token': default_token_generator.make_token(user),
                        'protocol': 'https' if request.is_secure() else 'http',
                    }
                    email_content = render_to_string(email_template_name, context)
                    try:
                        send_mail(
                            subject,
                            email_content,
                            settings.DEFAULT_FROM_EMAIL,
                            [user.email],
                            fail_silently=False,
                        )
                    except Exception as e:
                        return HttpResponse(f'Lỗi khi gửi email: {e}')
                
                messages.success(request, "Chúng tôi đã gửi cho bạn một email với hướng dẫn để đặt lại mật khẩu của bạn. Nếu một tài khoản có tồn tại với email bạn đã nhập, bạn sẽ nhận được nó.")
                return redirect("password_reset_done")
    else:
        form = PasswordResetForm()
    return render(
        request=request,
        template_name="auth/password_reset_form.html",
        context={"form": form}
    )

@login_required(login_url='login')
def logout_view(request):
    """User logout view"""
    history_key = f'gemini_chat_history_user_{request.user.id}'
    cache.delete(history_key)
    logout(request)
    messages.success(request, 'Bạn đã đăng xuất thành công!')
    return redirect('home')

@login_required(login_url='login')
def progress_view(request):
    """Display student's learning progress."""
    if request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager):
        return redirect('dashboard')

    user_profile = get_object_or_404(UserProfile, user=request.user)
    enrolled_courses = CourseEnrollment.objects.filter(user_profile=user_profile).select_related('course')
    enrolled_course_ids = enrolled_courses.values_list('course_id', flat=True)
    available_courses = Course.objects.exclude(id__in=enrolled_course_ids)

    context = {
        'user_profile': user_profile,
        'enrolled_courses': enrolled_courses,
        'available_courses': available_courses,
    }
    return render(request, 'pages/progress.html', context)

@login_required(login_url='login')
def dashboard(request):
    """Admin-only dashboard."""
    if not request.user.is_staff and not (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager):
        return redirect('progress')

    total_users = User.objects.count()
    total_courses = Course.objects.count()
    total_enrollments = CourseEnrollment.objects.count()
    total_reviews = CourseReview.objects.count()
    total_symbols = Symbol.objects.count()

    # Fetch active AI Provider and Model
    active_provider = AIProvider.objects.filter(is_active=True).first()
    active_api_model = APIModel.objects.filter(is_active=True).first()

    enrollment_data = CourseEnrollment.objects.annotate(month=TruncMonth('enrolled_at')) \
        .values('month').annotate(count=Count('id')).order_by('month')
    enrollment_labels = [e['month'].strftime('%Y-%m') for e in enrollment_data]
    enrollment_counts = [e['count'] for e in enrollment_data]

    completion_data = CourseEnrollment.objects.values('completed') \
        .annotate(count=Count('id')).order_by('completed')
    completion_labels = ['Chưa hoàn thành', 'Đã hoàn thành']
    completion_counts = [0, 0]
    for item in completion_data:
        if item['completed']:
            completion_counts[1] = item['count']
        else:
            completion_counts[0] = item['count']

    context = {
        'total_users': total_users,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'total_reviews': total_reviews,
        'total_symbols': total_symbols,
        'active_provider': active_provider,
        'active_api_model': active_api_model,
        'enrollment_labels': json.dumps(enrollment_labels),
        'enrollment_counts': json.dumps(enrollment_counts),
        'completion_labels': json.dumps(completion_labels),
        'completion_counts': json.dumps(completion_counts),
        'available_courses': Course.objects.all().order_by('-created_at')[:5]
    }
    return render(request, 'pages/dashboard.html', context)

def language_detail(request, id):
    """View details of a specific language"""
    language = get_object_or_404(SymbolicLanguage, id=id)
    context = {'language': language}
    return render(request, 'courses/language_detail.html', context)

def course_list(request):
    """List all available courses with filtering and search"""
    query = request.GET.get('q')
    category = request.GET.get('category')
    difficulty = request.GET.get('difficulty')

    courses = Course.objects.all()

    if query:
        courses = courses.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if category:
        courses = courses.filter(category=category)
    if difficulty:
        courses = courses.filter(difficulty=difficulty)

    categories = Course.objects.values_list('category', flat=True).distinct()
    difficulties = Course.objects.values_list('difficulty', flat=True).distinct()

    enrolled_ids = []
    if request.user.is_authenticated:
        enrolled_ids = CourseEnrollment.objects.filter(user_profile__user=request.user).values_list('course_id', flat=True)
    
    context = {
        'courses': courses,
        'enrolled_ids': enrolled_ids,
        'categories': categories,
        'difficulties': difficulties,
        'query': query,
        'selected_category': category,
        'selected_difficulty': difficulty,
    }
    return render(request, 'courses/courses.html', context)

def course_detail(request, id):
    """View a specific course and enrollment information"""
    course = get_object_or_404(Course, id=id)
    chapters = course.chapters.all()
    reviews = CourseReview.objects.filter(enrollment__course=course).select_related('enrollment__user_profile__user')
    related_courses = Course.objects.filter(category=course.category).exclude(id=course.id)[:3]

    is_enrolled = False
    enrollment = None
    review = None

    if request.user.is_authenticated:
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            enrollment = CourseEnrollment.objects.get(user_profile=user_profile, course=course)
            is_enrolled = True
            review = CourseReview.objects.filter(enrollment=enrollment).first()
        except (UserProfile.DoesNotExist, CourseEnrollment.DoesNotExist):
            pass

    context = {
        'course': course,
        'chapters': chapters,
        'is_enrolled': is_enrolled,
        'enrollment': enrollment,
        'review': review, 
        'reviews': reviews,
        'related_courses': related_courses,
    }
    return render(request, 'courses/course_detail.html', context)

@login_required(login_url='login')
def chapter_exercises(request, chapter_id):
    """Display exercises for a chapter."""
    chapter = get_object_or_404(Chapter, id=chapter_id)
    enrollment = CourseEnrollment.objects.filter(user_profile__user=request.user, course=chapter.course).first()

    if not enrollment:
        messages.error(request, "Bạn phải ghi danh vào khóa học để xem các bài tập.")
        return redirect('course_detail', id=chapter.course.id)

    exercises = chapter.exercises.all().order_by('order')
    completed_exercises = UserExerciseCompletion.objects.filter(user=request.user, exercise__in=exercises).values_list('exercise_id', flat=True)

    context = {
        'chapter': chapter,
        'exercises': exercises,
        'completed_exercises': list(completed_exercises),
    }
    return render(request, 'courses/chapter_exercises.html', context)

@login_required(login_url='login')
def exercise_detail(request, exercise_id):
    exercise = get_object_or_404(Exercise.objects.select_related('chapter__course'), id=exercise_id)
    chapter = exercise.chapter
    
    enrollment = CourseEnrollment.objects.filter(user_profile__user=request.user, course=chapter.course).first()
    if not enrollment:
        messages.error(request, "Bạn phải ghi danh vào khóa học để làm bài tập.")
        return redirect('course_detail', id=chapter.course.id)

    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        video_file = request.FILES.get('video')
        if not video_file:
            return JsonResponse({'error': 'Không có video được gửi.'}, status=400)

        try:
            correct_answer = exercise.answer.correct_answer.strip()
        except Answer.DoesNotExist:
            return JsonResponse({'error': 'Lỗi: Bài tập này chưa được cấu hình đáp án. Vui lòng liên hệ quản trị viên.'}, status=500)

        prediction, error = predict_from_video_file(video_file)
        if error:
            return JsonResponse({'error': error}, status=500)
        
        is_correct = prediction.lower() == correct_answer.lower()

        if is_correct:
            UserExerciseCompletion.objects.get_or_create(user=request.user, exercise=exercise)
            enrollment.save() # Recalculate progress
        
        next_exercise = Exercise.objects.filter(chapter=chapter, order__gt=exercise.order).order_by('order').first()
        
        response_data = {
            'correct': is_correct,
            'prediction': prediction,
            'correct_answer': correct_answer,
            'next_exercise_url': reverse('exercise_detail', args=[next_exercise.id]) if next_exercise else None
        }
        return JsonResponse(response_data)

    is_completed = UserExerciseCompletion.objects.filter(user=request.user, exercise=exercise).exists()
    next_exercise = Exercise.objects.filter(chapter=chapter, order__gt=exercise.order).order_by('order').first()
    prev_exercise = Exercise.objects.filter(chapter=chapter, order__lt=exercise.order).order_by('-order').first()

    context = {
        'exercise': exercise,
        'is_completed': is_completed,
        'next_exercise': next_exercise,
        'prev_exercise': prev_exercise,
        'chapter': chapter
    }
    return render(request, 'courses/exercise_detail.html', context)

@login_required(login_url='login')
@require_POST
def enroll_course(request, id):
    """Enroll the user in a course"""
    course = get_object_or_404(Course, id=id)
    user_profile = UserProfile.objects.get(user=request.user)
    enrollment, created = CourseEnrollment.objects.get_or_create(user_profile=user_profile, course=course)
    if created:
        messages.success(request, f'Bạn đã ghi danh khoá học: {course.title}')
    else:
        messages.info(request, 'Bạn đã đăng ký khoá học này rồi.')
    return redirect('course_detail', id=id)

@login_required(login_url='login')
def update_course_progress(request, id):
    """Update course progress for the logged-in user"""
    course = get_object_or_404(Course, id=id)
    try:
        enrollment = CourseEnrollment.objects.get(user_profile__user=request.user, course=course)
    except CourseEnrollment.DoesNotExist:
        messages.error(request, 'Bạn cần ghi danh khoá học trước khi cập nhật tiến độ.')
        return redirect('course_detail', id=id)

    if request.method == 'POST':
        exercise_id = request.POST.get('exercise_id')
        user_answer = request.POST.get('user_answer')
        exercise = get_object_or_404(Exercise, id=exercise_id)
        
        if exercise.answer.correct_answer == user_answer:
            UserExerciseCompletion.objects.get_or_create(user=request.user, exercise=exercise)
            messages.success(request, 'Correct answer!')
        else:
            messages.error(request, 'Incorrect answer. Please try again.')

        enrollment.save() # Recalculate progress

    return redirect('course_detail', id=id)


@login_required(login_url='login')
def review_course(request, id):
    """Submit a course review"""
    course = get_object_or_404(Course, id=id)
    try:
        enrollment = CourseEnrollment.objects.get(user_profile__user=request.user, course=course)
    except CourseEnrollment.DoesNotExist:
        messages.error(request, 'Bạn cần ghi danh khoá học trước khi đánh giá.')
        return redirect('course_detail', id=id)

    rating = int(request.POST.get('rating', 5))
    comment = request.POST.get('comment', '').strip()
    review, created = CourseReview.objects.get_or_create(enrollment=enrollment)
    review.rating = rating
    review.comment = comment
    review.save()
    messages.success(request, 'Cảm ơn bạn đã gửi đánh giá.')
    return redirect('course_detail', id=id)

@login_required(login_url='login')
def add_language(request, id):
    """Add language to user's learned languages"""
    language = get_object_or_404(SymbolicLanguage, id=id)
    user_profile = UserProfile.objects.get(user=request.user)
    user_profile.learned_languages.add(language)
    messages.success(request, f'Bạn đã học thêm: {language.title}')
    return redirect('progress')

@login_required(login_url='login')
def add_course(request):
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('dashboard')
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        difficulty = request.POST.get('difficulty')
        duration = request.POST.get('duration')
        if title and description and category and difficulty and duration:
            Course.objects.create(
                title=title,
                description=description,
                category=category,
                difficulty=difficulty,
                duration=duration
            )
            messages.success(request, 'Course added successfully.')
            return redirect('course_management')
        else:
            messages.error(request, 'Please fill out all fields.')
            return render(request, 'courses/course_form.html', {'action': 'Add'})
    return render(request, 'courses/course_form.html', {'action': 'Add'})

@login_required(login_url='login')
def edit_course(request, id):
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('dashboard')
    course = get_object_or_404(Course, id=id)
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category = request.POST.get('category')
        difficulty = request.POST.get('difficulty')
        duration = request.POST.get('duration')
        if title and description and category and difficulty and duration:
            course.title = title
            course.description = description
            course.category = category
            course.difficulty = difficulty
            course.duration = duration
            course.save()
            messages.success(request, 'Course updated successfully.')
            return redirect('course_management')
        else:
            messages.error(request, 'Please fill out all fields.')
            return render(request, 'courses/course_form.html', {'action': 'Edit', 'course': course})
    return render(request, 'courses/course_form.html', {'action': 'Edit', 'course': course})

@login_required(login_url='login')
def delete_course(request, id):
    if not request.user.is_staff:
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('dashboard')
    course = get_object_or_404(Course, id=id)
    if request.method == 'POST':
        course.delete()
        messages.success(request, 'Course deleted successfully.')
    return redirect('course_management')

@login_required
def course_management(request):
    """View to manage all courses for admins."""
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('dashboard')
    
    courses = Course.objects.all().order_by('-created_at')
    context = {
        'courses': courses
    }
    return render(request, 'courses/course_list_management.html', context)

# --- Chapter and Exercise Management ---
@login_required
def add_chapter(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('course_management')

    if request.method == 'POST':
        title = request.POST.get('title')
        order = request.POST.get('order')
        Chapter.objects.create(course=course, title=title, order=order)
        messages.success(request, 'Chapter added successfully.')
        return redirect('edit_course', id=course_id)

    return render(request, 'courses/chapter_form.html', {'course': course, 'action': 'Add'})

@login_required
def edit_chapter(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('course_management')

    if request.method == 'POST':
        chapter.title = request.POST.get('title')
        chapter.order = request.POST.get('order')
        chapter.save()
        messages.success(request, 'Chapter updated successfully.')
        return redirect('edit_course', id=chapter.course.id)

    return render(request, 'courses/chapter_form.html', {'chapter': chapter, 'action': 'Edit'})

@login_required
def delete_chapter(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('course_management')

    course_id = chapter.course.id
    chapter.delete()
    messages.success(request, 'Chapter deleted successfully.')
    return redirect('edit_course', id=course_id)

@login_required
def add_exercise(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('course_management')

    if request.method == 'POST':
        question = request.POST.get('question')
        order = request.POST.get('order')
        correct_answer = request.POST.get('correct_answer')
        exercise = Exercise.objects.create(chapter=chapter, question=question, order=order)
        Answer.objects.create(exercise=exercise, correct_answer=correct_answer)
        messages.success(request, 'Exercise added successfully.')
        return redirect('edit_course', id=chapter.course.id)

    return render(request, 'courses/exercise_form.html', {'chapter': chapter, 'action': 'Add'})

@login_required
def edit_exercise(request, exercise_id):
    exercise = get_object_or_404(Exercise, id=exercise_id)
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('course_management')

    if request.method == 'POST':
        exercise.question = request.POST.get('question')
        exercise.order = request.POST.get('order')
        exercise.answer.correct_answer = request.POST.get('correct_answer')
        exercise.save()
        exercise.answer.save()
        messages.success(request, 'Exercise updated successfully.')
        return redirect('edit_course', id=exercise.chapter.course.id)

    return render(request, 'courses/exercise_form.html', {'exercise': exercise, 'action': 'Edit'})

@login_required
def delete_exercise(request, exercise_id):
    exercise = get_object_or_404(Exercise, id=exercise_id)
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('course_management')

    course_id = exercise.chapter.course.id
    exercise.delete()
    messages.success(request, 'Exercise deleted successfully.')
    return redirect('edit_course', id=course_id)

# --- AI MODEL MANAGEMENT (ADMIN) --- #

@login_required
def model_management(request):
    """View to manage AI Models for admins."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('dashboard')
    
    models = AIModel.objects.all().order_by('-is_active', 'name')
    context = {
        'models': models,
        'page_title': 'Quản Lý Model AI'
    }
    return render(request, 'models/model_management.html', context)

@login_required
def model_form(request, id=None):
    """View to add or edit an AI Model, now with file upload."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')
    
    if id:
        model_instance = get_object_or_404(AIModel, id=id)
        page_title = 'Sửa Model AI'
    else:
        model_instance = None
        page_title = 'Thêm Model AI'

    if request.method == 'POST':
        name = request.POST.get('name')
        is_active = request.POST.get('is_active') == 'on'
        model_file = request.FILES.get('model_file')

        # --- Validation ---
        if not name:
            messages.error(request, 'Vui lòng nhập Tên Model.')
            return render(request, 'models/model_form.html', {'page_title': page_title, 'model': model_instance})

        if not model_instance and not model_file:
            messages.error(request, 'Vui lòng tải lên một tệp model.')
            return render(request, 'models/model_form.html', {'page_title': page_title, 'model': model_instance, 'name': name})
            
        if model_file:
            ext = os.path.splitext(model_file.name)[1]
            if ext.lower() not in ['.h5', '.keras']:
                messages.error(request, 'Định dạng tệp không hợp lệ. Chỉ chấp nhận .h5 hoặc .keras.')
                return render(request, 'models/model_form.html', {'page_title': page_title, 'model': model_instance, 'name': name})

        # --- Process Data ---
        instance_id = model_instance.id if model_instance else None
        
        if AIModel.objects.filter(name=name).exclude(id=instance_id).exists():
             messages.error(request, f'Model với tên "{name}" đã tồn tại.')
        else:
            if model_instance:
                instance_to_save = model_instance
            else:
                instance_to_save = AIModel()

            instance_to_save.name = name
            
            if model_file:
                fs = FileSystemStorage(location=os.path.join(settings.BASE_DIR, 'Models'))
                if instance_to_save.pk and instance_to_save.file_path and fs.exists(instance_to_save.file_path):
                     try:
                        fs.delete(instance_to_save.file_path)
                     except Exception as e:
                        print(f"Could not delete old model file: {e}")
                
                filename = fs.save(model_file.name, model_file)
                instance_to_save.file_path = os.path.join('Models', filename)

            if is_active and (not instance_to_save.is_active):
                cache.delete('active_ai_model')
            
            instance_to_save.is_active = is_active
            instance_to_save.save()
            
            action_str = "Sửa" if id else "Thêm"
            messages.success(request, f'Đã {action_str.lower()} model "{name}" thành công.')
            return redirect('model_management')

    context = {
        'model': model_instance,
        'page_title': page_title
    }
    return render(request, 'models/model_form.html', context)

@login_required
@require_POST
def delete_model(request, id):
    """Deletes an AI Model."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')
    
    model_to_delete = get_object_or_404(AIModel, id=id)
    if model_to_delete.is_active:
        messages.error(request, 'Bạn không thể xóa một model đang hoạt động.')
    else:
        name = model_to_delete.name
        model_to_delete.delete()
        messages.success(request, f'Đã xóa model "{name}" thành công.')
    return redirect('model_management')

@login_required
def set_active_model(request, id):
    """Sets an AI model as active."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    model_to_activate = get_object_or_404(AIModel, id=id)
    if not model_to_activate.is_active:
        model_to_activate.is_active = True
        model_to_activate.save()
        cache.delete('active_ai_model')
        messages.success(request, f'Đã kích hoạt model "{model_to_activate.name}".')
    else:
        messages.info(request, f'Model "{model_to_activate.name}" đã được kích hoạt rồi.')
        
    return redirect('model_management')

# --- Chatbot API Management ---
@login_required
def chatbot_api_management(request):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('dashboard')
    
    providers = AIProvider.objects.all().prefetch_related('api_models')
    context = {
        'providers': providers,
        'page_title': 'Quản lý API Chatbot'
    }
    return render(request, 'chat/chatbot_api_management.html', context)

@login_required
def chatbot_api_form(request, id=None):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    if id:
        provider = get_object_or_404(AIProvider.objects.prefetch_related('api_models'), id=id)
        page_title = f'Sửa nhà cung cấp: {provider.name}'
    else:
        provider = None
        page_title = 'Thêm nhà cung cấp API'

    if request.method == 'POST':
        if 'save_provider' in request.POST:
            name = request.POST.get('name')
            api_key = request.POST.get('api_key')

            if not name or not api_key:
                messages.error(request, 'Tên và API Key không được để trống.')
                return render(request, 'chat/chatbot_api_form.html', {'provider': provider, 'page_title': page_title})

            if provider:
                provider.name = name
                provider.api_key = api_key
                provider.save()
                messages.success(request, f'Đã cập nhật nhà cung cấp "{name}" thành công.')
                return redirect('chatbot_api_management')
            else:
                if AIProvider.objects.filter(name=name).exists():
                    messages.error(request, f'Nhà cung cấp với tên "{name}" đã tồn tại.')
                    return render(request, 'chat/chatbot_api_form.html', {'page_title': page_title})
                
                new_provider = AIProvider.objects.create(name=name, api_key=api_key)
                messages.success(request, f'Đã thêm nhà cung cấp "{name}" thành công.')
                return redirect('edit_chatbot_api', id=new_provider.id)

        elif 'add_model' in request.POST:
            if not provider:
                 messages.error(request, 'Không tìm thấy nhà cung cấp để thêm model.')
                 return redirect('chatbot_api_management')

            model_name = request.POST.get('model_name')
            if model_name:
                APIModel.objects.create(provider=provider, model_name=model_name)
                messages.success(request, f'Đã thêm model "{model_name}" vào nhà cung cấp "{provider.name}".')
            else:
                messages.error(request, 'Tên model không được để trống.')
            
            return redirect('edit_chatbot_api', id=provider.id)

    context = {
        'provider': provider,
        'page_title': page_title
    }
    return render(request, 'chat/chatbot_api_form.html', context)

@login_required
@require_POST
def delete_chatbot_api(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')
    
    provider = get_object_or_404(AIProvider, id=id)
    name = provider.name
    provider.delete()
    messages.success(request, f'Đã xóa nhà cung cấp "{name}" thành công.')
    return redirect('chatbot_api_management')

@login_required
@require_POST
def set_active_provider(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('chatbot_api_management')

    AIProvider.objects.update(is_active=False)
    provider = get_object_or_404(AIProvider, id=id)
    provider.is_active = True
    provider.save()
    messages.success(request, f'Đã kích hoạt nhà cung cấp "{provider.name}".')
    return redirect('chatbot_api_management')

@login_required
@require_POST
def set_active_api_model(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('chatbot_api_management')

    model = get_object_or_404(APIModel, id=id)
    APIModel.objects.filter(provider=model.provider).update(is_active=False)
    model.is_active = True
    model.save()
    messages.success(request, f'Đã kích hoạt model "{model.model_name}" cho nhà cung cấp "{model.provider.name}".')
    return redirect('edit_chatbot_api', id=model.provider.id)

@login_required
@require_POST
def delete_api_model(request, id):
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    model = get_object_or_404(APIModel, id=id)
    provider_id = model.provider.id
    model_name = model.model_name
    
    if model.is_active:
        messages.error(request, f'Không thể xóa model "{model_name}" đang hoạt động.')
    else:
        model.delete()
        messages.success(request, f'Đã xóa model "{model_name}" thành công.')

    return redirect('edit_chatbot_api', id=provider_id)


# --- USER MANAGEMENT (ADMIN) --- #

@login_required(login_url='login')
def user_list(request):
    """Lists all users for the admin."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')
    
    users = User.objects.all().order_by('username')
    context = {
        'users': users,
        'page_title': 'Quản Lý Người Dùng'
    }
    return render(request, 'pages/user_list.html', context)

@login_required(login_url='login')
def user_add(request):
    """Adds a new user from the admin panel."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        is_staff = request.POST.get('is_staff') == 'on'
        is_manager = request.POST.get('is_manager') == 'on'

        if password != password2:
            messages.error(request, 'Mật khẩu không khớp.')
            return render(request, 'pages/user_form.html', {'action': 'Thêm', 'page_title': 'Thêm Người Dùng'})
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Tên người dùng đã tồn tại.')
            return render(request, 'pages/user_form.html', {'action': 'Thêm', 'page_title': 'Thêm Người Dùng'})

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_staff = is_staff
        user.save()
        
        user_profile, created = UserProfile.objects.get_or_create(user=user)
        user_profile.is_manager = is_manager
        user_profile.save()
        
        messages.success(request, f'Người dùng "{username}" đã được tạo thành công.')
        return redirect('user_list')
    
    return render(request, 'pages/user_form.html', {'action': 'Thêm', 'page_title': 'Thêm Người Dùng'})

@login_required(login_url='login')
def user_edit(request, id):
    """Edits an existing user from the admin panel."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')

    user_to_edit = get_object_or_404(User, id=id)
    user_profile, created = UserProfile.objects.get_or_create(user=user_to_edit)

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        is_manager = request.POST.get('is_manager') == 'on'
        
        user_to_edit.email = email
        user_profile.is_manager = is_manager
        user_profile.save()

        if request.user.id != user_to_edit.id:
            is_staff = request.POST.get('is_staff') == 'on'
            user_to_edit.is_staff = is_staff

        if password:
            if password != password2:
                messages.error(request, 'Mật khẩu không khớp.')
                return render(request, 'pages/user_form.html', {
                    'action': 'Sửa', 
                    'page_title': 'Sửa Người Dùng', 
                    'user_to_edit': user_to_edit
                })
            user_to_edit.set_password(password)

        user_to_edit.save()
        messages.success(request, f'Người dùng "{user_to_edit.username}" đã được cập nhật thành công.')
        return redirect('user_list')

    return render(request, 'pages/user_form.html', {
        'action': 'Sửa', 
        'page_title': 'Sửa Người Dùng', 
        'user_to_edit': user_to_edit
    })

@login_required(login_url='login')
@require_POST
def user_delete(request, id):
    """Deletes a user."""
    if not request.user.is_staff:
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('dashboard')
    
    if request.user.id == id:
        messages.error(request, "Bạn không thể xoá chính tài khoản của mình.")
        return redirect('user_list')

    user_to_delete = get_object_or_404(User, id=id)
    username = user_to_delete.username
    user_to_delete.delete()
    messages.success(request, f'Người dùng "{username}" đã được xoá.')
    return redirect('user_list')


# --- SYMBOL LIBRARY MANAGEMENT (ADMIN/MANAGER) --- #

@login_required(login_url='login')
def symbol_library_management(request):
    """
    Main view for managing the symbol library. Lists all categories and their symbols.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('dashboard')

    categories = SymbolCategory.objects.all().prefetch_related('symbols')
    category_form = SymbolCategoryForm()

    context = {
        'categories': categories,
        'category_form': category_form,
        'page_title': 'Quản lý Thư viện Ký hiệu'
    }
    return render(request, 'symbols/symbol_library_management.html', context)


@login_required(login_url='login')
@require_POST
def add_symbol_category(request):
    """
    Handles the creation of a new symbol category.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('symbol_library_management')

    form = SymbolCategoryForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, f"Đã thêm danh mục '{form.cleaned_data['name']}' thành công.")
    else:
        error_msg = ' '.join([' '.join(errors) for field, errors in form.errors.items()])
        messages.error(request, f"Lỗi khi thêm danh mục: {error_msg}")

    return redirect('symbol_library_management')


@login_required(login_url='login')
def edit_symbol_category(request, category_id):
    """
    Handles editing an existing symbol category.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('symbol_library_management')

    category = get_object_or_404(SymbolCategory, id=category_id)
    if request.method == 'POST':
        form = SymbolCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật danh mục '{category.name}' thành công.")
            return redirect('symbol_library_management')
    else:
        form = SymbolCategoryForm(instance=category)

    context = {
        'form': form,
        'category': category,
        'page_title': f"Sửa danh mục: {category.name}"
    }
    return render(request, 'symbols/symbol_category_form.html', context)


@login_required(login_url='login')
@require_POST
def delete_symbol_category(request, category_id):
    """
    Handles deleting a symbol category.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('symbol_library_management')
    
    category = get_object_or_404(SymbolCategory, id=category_id)
    if category.symbols.exists():
        messages.error(request, f"Không thể xóa danh mục '{category.name}' vì nó vẫn còn chứa các ký hiệu.")
    else:
        name = category.name
        category.delete()
        messages.success(request, f"Đã xóa danh mục '{name}' thành công.")
    
    return redirect('symbol_library_management')


@login_required(login_url='login')
def add_symbol(request, category_id):
    """
    Handles adding a new symbol to a specific category.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('symbol_library_management')
    
    category = get_object_or_404(SymbolCategory, id=category_id)
    if request.method == 'POST':
        form = SymbolForm(request.POST, request.FILES)
        if form.is_valid():
            symbol = form.save(commit=False)
            symbol.category = category
            symbol.save()
            messages.success(request, f"Đã thêm ký hiệu '{symbol.name}' vào danh mục '{category.name}'.")
            return redirect('symbol_library_management')
    else:
        form = SymbolForm(initial={'category': category})

    context = {
        'form': form,
        'category': category,
        'page_title': f"Thêm ký hiệu vào '{category.name}'",
        'action': 'Thêm'
    }
    return render(request, 'symbols/symbol_form.html', context)


@login_required(login_url='login')
def edit_symbol(request, symbol_id):
    """
    Handles editing an existing symbol.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('symbol_library_management')

    symbol = get_object_or_404(Symbol, id=symbol_id)
    if request.method == 'POST':
        form = SymbolForm(request.POST, request.FILES, instance=symbol)
        if form.is_valid():
            form.save()
            messages.success(request, f"Đã cập nhật ký hiệu '{symbol.name}' thành công.")
            return redirect('symbol_library_management')
    else:
        form = SymbolForm(instance=symbol)

    context = {
        'form': form,
        'symbol': symbol,
        'category': symbol.category,
        'page_title': f"Sửa ký hiệu: {symbol.name}",
        'action': 'Sửa'
    }
    return render(request, 'symbols/symbol_form.html', context)


@login_required(login_url='login')
@require_POST
def delete_symbol(request, symbol_id):
    """
    Handles deleting a symbol.
    """
    if not (request.user.is_staff or (hasattr(request.user, 'userprofile') and request.user.userprofile.is_manager)):
        messages.error(request, 'Bạn không có quyền thực hiện hành động này.')
        return redirect('symbol_library_management')

    symbol = get_object_or_404(Symbol, id=symbol_id)
    name = symbol.name
    symbol.delete()
    messages.success(request, f"Đã xóa ký hiệu '{name}' thành công.")
    
    return redirect('symbol_library_management')

# --- SYMBOL LIBRARY PUBLIC VIEWS --- #

@login_required(login_url='login')
def symbol_library_view(request):
    """Displays all symbol categories for the public."""
    categories = SymbolCategory.objects.annotate(symbol_count=Count('symbols')).filter(symbol_count__gt=0)
    context = {
        'categories': categories,
        'page_title': 'Thư viện Ký hiệu'
    }
    return render(request, 'symbols/symbol_library.html', context)

@login_required(login_url='login')
def symbol_category_detail_view(request, category_slug):
    """Displays a list of symbols in a specific category."""
    category = get_object_or_404(SymbolCategory, slug=category_slug)
    symbols = category.symbols.all()
    context = {
        'category': category,
        'symbols': symbols,
        'page_title': f'Thư viện: {category.name}'
    }
    return render(request, 'symbols/symbol_category_detail.html', context)

@login_required(login_url='login')
def symbol_detail_view(request, symbol_slug):
    """Displays the details of a single symbol, including next and previous symbols."""
    symbol = get_object_or_404(Symbol.objects.select_related('category'), slug=symbol_slug)

    # Get all symbols in the same category, ordered by name
    symbols_in_category = list(Symbol.objects.filter(category=symbol.category).order_by('name'))

    try:
        current_index = symbols_in_category.index(symbol)
    except ValueError:
        # Should not happen, but as a fallback
        current_index = -1
        prev_symbol = None
        next_symbol = None
    else:
        # Determine previous symbol
        prev_symbol = symbols_in_category[current_index - 1] if current_index > 0 else None
        
        # Determine next symbol
        next_symbol = symbols_in_category[current_index + 1] if current_index < len(symbols_in_category) - 1 else None

    context = {
        'symbol': symbol,
        'page_title': f'Ký hiệu: {symbol.name}',
        'prev_symbol': prev_symbol,
        'next_symbol': next_symbol
    }
    return render(request, 'symbols/symbol_detail.html', context)


@login_required
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=user_profile)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Hồ sơ của bạn đã được cập nhật thành công!')
                return redirect('profile')
        
        elif 'change_password' in request.POST:
            password_form = CustomPasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # Important!
                messages.success(request, 'Mật khẩu của bạn đã được thay đổi thành công.')
                return redirect('profile')
            else:
                # This is so the other forms still have their data
                user_form = UserUpdateForm(instance=request.user)
                profile_form = ProfileUpdateForm(instance=user_profile)

    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=user_profile)
        password_form = CustomPasswordChangeForm(request.user)

    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'pages/profile.html', context)


# --- Blog Views --- #

@login_required(login_url='login')
def blog_feed(request):
    post_form = PostForm()
    comment_form = CommentForm()

    # Annotate posts with like count and whether the current user has liked it
    user_liked = Like.objects.filter(post=OuterRef('pk',), user=request.user)
    posts = Post.objects.all() \
        .select_related('author__userprofile') \
        .prefetch_related('comments__author__userprofile') \
        .annotate(like_count=Count('likes', distinct=True), user_has_liked=Exists(user_liked)) \
        .order_by('-created_at')

    context = {
        'posts': posts,
        'post_form': post_form,
        'comment_form': comment_form,
    }
    return render(request, 'blog/blog_feed.html', context)

@login_required(login_url='login')
@require_POST
def create_post(request):
    form = PostForm(request.POST, request.FILES)
    if form.is_valid():
        post = form.save(commit=False)
        post.author = request.user
        post.save()
        messages.success(request, 'Đã đăng bài thành công!')
    else:
        messages.error(request, 'Đã có lỗi xảy ra. Vui lòng thử lại.')
    return redirect('blog_feed')

@login_required(login_url='login')
@require_POST
def add_comment_to_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        comment.save()
        
        # Prepare the comment data to be sent back as JSON
        comment_data = {
            'id': comment.id,
            'author': {
                'username': comment.author.username,
                'avatar': comment.author.userprofile.avatar.url if comment.author.userprofile.avatar else None,
            },
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
            'content': comment.content,
        }
        return JsonResponse({'status': 'ok', 'comment': comment_data})
    else:
        return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)


@login_required(login_url='login')
@require_POST
def toggle_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    
    if not created:
        like.delete()
        liked = False
    else:
        liked = True

    post.refresh_from_db()

    return JsonResponse({'status': 'ok', 'liked': liked, 'like_count': post.likes.count()})

@login_required(login_url='login')
@require_POST
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.author == request.user or request.user.is_staff:
        post.delete()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền xoá bài đăng này.'}, status=403)

@login_required(login_url='login')
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author == request.user or request.user.is_staff:
        comment.delete()
        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền xoá bình luận này.'}, status=403)

@login_required(login_url='login')
def get_post_details(request, post_id):
    """
    Returns the like count and comment count for a given post.
    """
    post = get_object_or_404(Post, id=post_id)
    user_liked = Like.objects.filter(post=post, user=request.user).exists()
    
    comments = post.comments.select_related('author__userprofile').order_by('created_at')
    
    comments_data = [{
        'id': c.id,
        'author': {
            'username': c.author.username,
            'avatar_url': c.author.userprofile.avatar.url if c.author.userprofile.avatar else None
        },
        'content': c.content,
        'created_at': c.created_at.strftime('%b. %d, %Y, %I:%M %p')
    } for c in comments]

    data = {
        'like_count': post.likes.count(),
        'user_has_liked': user_liked,
        'comments': comments_data,
        'comment_count': post.comments.count(),
    }
    return JsonResponse(data)

# --- Live Chat Support Views ---

@login_required
def inbox_view(request):
    if not (request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)):
        messages.error(request, "Bạn không có quyền truy cập trang này.")
        return redirect('home')

    latest_message = Message.objects.filter(conversation=OuterRef('pk')).order_by('-timestamp')

    # Managers see unassigned conversations and conversations assigned to them
    conversations = Conversation.objects.filter(
        Q(assignee__isnull=True) | Q(assignee=request.user)
    ).annotate(
        latest_message_content=Subquery(latest_message.values('content')[:1]),
        latest_message_time=Subquery(latest_message.values('timestamp')[:1]),
        unread_count=Count('messages', filter=Q(messages__is_read=False) & ~Q(messages__sender=request.user))
    ).order_by('-latest_message_time')

    return render(request, 'chat/inbox.html', {'conversations': conversations})

@login_required
def conversation_detail_view(request, conversation_id):
    is_support_staff = request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)

    if not is_support_staff:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        # Staff can only access conversations that are assigned to them or are unassigned
        conversation = get_object_or_404(Conversation, Q(id=conversation_id) & (Q(assignee=request.user) | Q(assignee__isnull=True)))
        # If the conversation was unassigned, assign it to the current staff member upon viewing
        if conversation.assignee is None:
            conversation.assignee = request.user
            conversation.save()

    conversation.messages.filter(~Q(sender=request.user), is_read=False).update(is_read=True)

    messages_list = conversation.messages.all().order_by('timestamp')
    
    return render(request, 'chat/conversation_detail.html', {
        'conversation': conversation,
        'messages_list': messages_list,
        'is_support_staff': is_support_staff
    })

@login_required
def get_conversation_messages(request, conversation_id):
    is_support_staff = request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)

    if not is_support_staff:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        conversation = get_object_or_404(Conversation, id=conversation_id, assignee=request.user)

    last_message_id = request.GET.get('last_message_id')
    query = conversation.messages.select_related('sender', 'sender__userprofile')

    if last_message_id and last_message_id.isdigit():
        query = query.filter(id__gt=int(last_message_id))

    new_messages = query.order_by('timestamp')
    
    messages_data = [
        {
            'id': msg.id,
            'sender': {
                'id': msg.sender.id,
                'username': msg.sender.username,
                'avatar_url': msg.sender.userprofile.avatar.url if hasattr(msg.sender, 'userprofile') and msg.sender.userprofile.avatar else None,
            },
            'content': msg.content,
            'timestamp': msg.timestamp.strftime('%H:%M')
        }
        for msg in new_messages
    ]

    for msg in new_messages:
        if msg.sender != request.user:
            msg.is_read = True
            msg.save(update_fields=['is_read'])
            
    return JsonResponse({'messages': messages_data})

@login_required
@csrf_exempt
@require_POST
def start_conversation_api(request):
    content = request.POST.get('content')
    if not content:
        return JsonResponse({'status': 'error', 'message': 'Nội dung tin nhắn không được để trống.'}, status=400)

    conversation, created = Conversation.objects.get_or_create(user=request.user)
    
    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content
    )
    
    return JsonResponse({
        'status': 'success',
        'message': 'Tin nhắn đã được gửi.',
        'conversation_id': conversation.id
    })

@login_required
@csrf_exempt
@require_POST
def send_reply_api(request, conversation_id):
    is_support_staff = request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)

    if not is_support_staff:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    else:
        conversation = get_object_or_404(Conversation, id=conversation_id, assignee=request.user)

    content = request.POST.get('content')
    if not content:
        return JsonResponse({'status': 'error', 'message': 'Nội dung không được để trống.'}, status=400)

    message = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=content
    )
    
    return JsonResponse({
        'status': 'success',
        'message': {
            'id': message.id,
            'sender': {
                'id': message.sender.id,
                'username': message.sender.username,
                'avatar_url': message.sender.userprofile.avatar.url if hasattr(message.sender, 'userprofile') and message.sender.userprofile.avatar else None
            },
            'content': message.content,
            'timestamp': message.timestamp.strftime('%H:%M')
        }
    })

@login_required
@require_POST
def assign_conversation_api(request, conversation_id):
    if not (request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)):
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền thực hiện hành động này.'}, status=403)
    
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if conversation.assignee is None:
        conversation.assignee = request.user
        conversation.save()
        return JsonResponse({'status': 'success', 'message': f'Cuộc trò chuyện đã được gán cho {request.user.username}'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Cuộc trò chuyện này đã được gán cho người khác.'}, status=400)

@login_required
@require_POST
def delete_conversation_api(request, conversation_id):
    if not (request.user.is_staff or getattr(request.user.userprofile, 'is_manager', False)):
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền thực hiện hành động này.'}, status=403)

    conversation = get_object_or_404(Conversation, id=conversation_id)
    if conversation.assignee == request.user:
        conversation.delete()
        return JsonResponse({'status': 'success', 'message': 'Cuộc trò chuyện đã được xóa.'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Bạn chỉ có thể xóa các cuộc trò chuyện được gán cho bạn.'}, status=403)

@login_required
def get_user_conversation_api(request):
    """Checks if a conversation exists for the current user and returns its ID."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User not authenticated'}, status=401)

    try:
        conversation = Conversation.objects.get(user=request.user)
        return JsonResponse({'conversation_id': conversation.id})
    except Conversation.DoesNotExist:
        return JsonResponse({})

@login_required
def check_unread_api(request):
    if request.user.is_staff or getattr(request.user, 'userprofile', {}).is_manager:
        unread_count = Message.objects.filter(
            Q(conversation__assignee=request.user) | Q(conversation__assignee__isnull=True),
            is_read=False
        ).exclude(sender=request.user).count()
    else:
        unread_count = Message.objects.filter(
            conversation__user=request.user, 
            is_read=False
        ).exclude(sender=request.user).count()
            
    return JsonResponse({'unread_count': unread_count})


@csrf_exempt
@require_http_methods(["POST"])
def clear_chat_history(request):
    """Clears the user's chatbot history."""
    try:
        if not request.session.session_key:
            request.session.create()

        data = json.loads(request.body)
        user_id = data.get('user_id')
        
        if user_id:
            history_key = f'gemini_chat_history_user_{user_id}'
        else:
            history_key = f'gemini_chat_history_session_{request.session.session_key}'

        cache.delete(history_key)
        
        initial_message = "Xin chào! Tôi là Trợ lý ảo của Ngôn Ngữ Ký Hiệu. Tôi có thể giúp gì cho bạn?"
        
        return JsonResponse({"status": "success", "message": "Lịch sử trò chuyện đã được xoá.", "initial_message": initial_message})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt
def gemini_chat(request):
    if request.method == 'POST':
        try:
            if not request.session.session_key:
                request.session.create()

            data = json.loads(request.body)
            user_id = data.get('user_id')
            user_message = data.get('message')
            history_from_client = data.get('history', [])

            if user_id:
                history_key = f'gemini_chat_history_user_{user_id}'
            else:
                history_key = f'gemini_chat_history_session_{request.session.session_key}'

            if not user_message:
                return JsonResponse({'error': 'No message provided'}, status=400)

            api_key = settings.GEMINI_API_KEY
            if not api_key:
                return JsonResponse({'error': 'Gemini API key not configured'}, status=500)

            genai.configure(api_key=api_key)

            # --- Tool Helper Functions ---
            def get_courses_list():
                """Gets a list of all available course titles."""
                try:
                    courses = Course.objects.all().values_list('title', flat=True)
                    if not courses:
                        return json.dumps({"status": "error", "message": "Hiện tại không có khóa học nào."})
                    return json.dumps({"status": "success", "courses": list(courses)})
                except Exception as e:
                    return json.dumps({"status": "error", "message": f"Lỗi khi truy vấn khóa học: {str(e)}"})

            def enroll_in_course(course_name: str):
                """Enrolls the logged-in user in a specific course by its name."""
                if not user_id:
                    return json.dumps({"status": "error", "message": "Bạn cần đăng nhập để ghi danh."})
                try:
                    user = User.objects.get(pk=user_id)
                    user_profile = UserProfile.objects.get(user=user)
                    course_to_enroll = Course.objects.get(title__iexact=course_name)

                    enrollment, created = CourseEnrollment.objects.get_or_create(
                        user_profile=user_profile, 
                        course=course_to_enroll
                    )

                    if created:
                        return json.dumps({"status": "success", "message": f"Bạn đã ghi danh thành công vào khóa học '{course_name}'."})
                    else:
                        return json.dumps({"status": "info", "message": f"Bạn đã ghi danh vào khóa học '{course_name}' từ trước rồi."})
                except (User.DoesNotExist, UserProfile.DoesNotExist):
                     return json.dumps({"status": "error", "message": "Không tìm thấy thông tin người dùng."})
                except Course.DoesNotExist:
                    return json.dumps({"status": "error", "message": f"Không tìm thấy khóa học với tên '{course_name}'."})
                except Exception as e:
                    return json.dumps({"status": "error", "message": f"Đã có lỗi xảy ra: {str(e)}"})

            def navigate_to_page(page_name: str):
                """
                Returns a JSON object with a URL for the frontend to navigate to.
                This is a special function that will cause an immediate JSON response to the client.
                """
                try:
                    page_map = {
                        'cộng đồng': 'blog_feed',
                        'blog': 'blog_feed',
                        'feed': 'blog_feed',
                        'dự đoán ai': 'predict_symbol',
                        'dự đoán': 'predict_symbol',
                        'ai': 'predict_symbol',
                        'thư viện': 'symbol_library',
                        'library': 'symbol_library',
                    }
                    normalized_page_name = page_name.lower().strip()
                    
                    if normalized_page_name in page_map:
                        url = reverse(page_map[normalized_page_name])
                        return {'status': 'success', 'action': 'navigate', 'url': url}
                    else:
                        return {'status': 'error', 'message': f"Tôi không tìm thấy trang nào có tên là '{page_name}'. Các trang có sẵn: Cộng đồng, Dự đoán AI, Thư viện."}
                except Exception as e:
                    return {'status': 'error', 'message': f"Đã xảy ra lỗi khi tìm trang: {str(e)}"}

            # --- Function & Tool Definitions ---
            available_functions = {
                "get_courses_list": get_courses_list,
                "enroll_in_course": enroll_in_course,
                "navigate_to_page": navigate_to_page,
            }
            
            tools = [
                genai.protos.Tool(function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name='get_courses_list',
                        description="Lấy danh sách tất cả các tiêu đề khóa học có sẵn.",
                        parameters=genai.protos.Schema()
                    ),
                    genai.protos.FunctionDeclaration(
                        name='enroll_in_course',
                        description="Ghi danh người dùng đã đăng nhập vào một khóa học cụ thể theo tên.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                'course_name': genai.protos.Schema(type=genai.protos.Type.STRING)
                            },
                            required=['course_name']
                        )
                    ),
                    genai.protos.FunctionDeclaration(
                        name='navigate_to_page',
                        description="Điều hướng người dùng đến một trang cụ thể. Chỉ sử dụng cho các trang: 'Cộng đồng', 'Dự đoán AI', và 'Thư viện'.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                'page_name': genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Tên của trang, ví dụ: 'Cộng đồng', 'Dự đoán AI', 'Thư viện'"
                                )
                            },
                            required=['page_name']
                        )
                    )
                ])
            ]
            
            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                },
                tools=tools
            )

            history = cache.get(history_key)

            if history is None:
                system_prompt = """
Bạn là 'Trợ lý ảo' của trang web 'Ngôn Ngữ Ký Hiệu'.
Nhiệm vụ của bạn là giúp người dùng bằng cách gọi các hàm (tools) được cung cấp.
Luôn trả lời bằng tiếng Việt.

QUY TẮC:
1.  **SỬ DỤNG HÀM**: Nhiệm vụ chính của bạn là gọi hàm.
    -   Nếu người dùng muốn đến các trang 'Cộng đồng', 'Dự đoán AI', hoặc 'Thư viện', hãy gọi hàm `navigate_to_page`.
    -   Nếu người dùng muốn xem các khóa học, hãy gọi `get_courses_list`.
    -   Nếu người dùng muốn đăng ký một khóa học, hãy gọi `enroll_in_course`.
2.  **LÀM RÕ**: Nếu không chắc chắn, hãy hỏi lại. Ví dụ: "Bạn muốn đăng ký khóa học nào?".
3.  **TRẢ LỜI TỪ KẾT QUẢ**: Dựa vào kết quả hàm trả về để tạo câu trả lời tự nhiên cho người dùng. Nếu hàm báo lỗi, hãy thông báo lỗi đó.
4.  **GIỚI HẠN**: Nếu câu hỏi không liên quan đến chức năng của trang web, hãy lịch sự từ chối: "Xin lỗi, tôi chỉ có thể giúp về các tính năng của trang web này."
5.  **VĂN BẢN THUẦN TÚY**: Không dùng Markdown (không có *, #, v.v.).

Bắt đầu cuộc trò chuyện.
"""
                history = [
                    {'role': 'user', 'parts': [system_prompt]},
                    {'role': 'model', 'parts': ["Xin chào! Tôi là Trợ lý ảo của Ngôn Ngữ Ký Hiệu. Tôi có thể giúp gì cho bạn?"]}
                ]

            chat_session = model.start_chat(history=history)
            response = chat_session.send_message(user_message)

            while response.candidates and response.candidates[0].content.parts and response.candidates[0].content.parts[0].function_call:
                function_call = response.candidates[0].content.parts[0].function_call
                function_name = function_call.name

                if function_name not in available_functions:
                    function_response_content = json.dumps({"status": "error", "message": "Chức năng không được hỗ trợ."})
                else:
                    function_to_call = available_functions[function_name]
                    function_args = {key: value for key, value in function_call.args.items()}
                    
                    result = function_to_call(**function_args)

                    if function_name == 'navigate_to_page' and result.get('action') == 'navigate' and result.get('status') == 'success':
                        return JsonResponse(result)
                    else:
                        function_response_content = json.dumps(result) if isinstance(result, dict) else result

                response = chat_session.send_message(
                    genai.protos.Part(function_response=genai.protos.FunctionResponse(
                        name=function_name,
                        response={'content': function_response_content}
                    ))
                )

            final_reply = response.text.replace('*', '')

            history_for_cache = [type(m).to_dict(m) for m in chat_session.history]
            cache.set(history_key, history_for_cache, timeout=3600)

            return JsonResponse({'reply': final_reply})
        except google_exceptions.ResourceExhausted:
            return JsonResponse({'reply': 'Rất tiếc, hệ thống đang tạm thời quá tải do vượt quá giới hạn yêu cầu. Vui lòng thử lại sau ít phút.'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)
