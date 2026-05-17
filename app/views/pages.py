import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_POST

from app.models import (
    UserProfile, Course, CourseEnrollment, CourseReview, 
    Symbol, AIProvider, APIModel
)

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
