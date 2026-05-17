from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from app.models import (
    SymbolicLanguage, UserProfile, Course, CourseEnrollment, CourseReview, 
    Chapter, Exercise, Answer, UserExerciseCompletion
)
from .utils import predict_from_video_file

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

    return render(request, 'courses/chapter_form.html', {'chapter': chapter, 'course': chapter.course, 'action': 'Edit'})

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
