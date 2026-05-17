from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import PasswordResetForm
from django.http import HttpResponse
from django.conf import settings
from django.db.models import Q
from django.core.cache import cache

from app.models import UserProfile, Course, CourseEnrollment
from app.forms import UserUpdateForm, ProfileUpdateForm, CustomPasswordChangeForm

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

        # Send activation email
        mail_subject = 'Kích hoạt tài khoản Ngôn Ngữ Ký Hiệu của bạn.'
        html_message = render_to_string('auth/account_activation_email.html', {
            'user': user,
            'domain': request.get_host(),
            'uid': urlsafe_base64_encode(force_bytes(user.pk)),
            'token': default_token_generator.make_token(user),
            'protocol': 'https' if request.is_secure() else 'http',
        })
        to_email = email
        
        send_mail(
            mail_subject, 
            'Vui lòng kích hoạt tài khoản của bạn.', 
            settings.DEFAULT_FROM_EMAIL, 
            [to_email], 
            html_message=html_message
        )

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
        
        try:
            latest_course = Course.objects.latest('created_at')
            user_profile = UserProfile.objects.get(user=user)
            CourseEnrollment.objects.create(user_profile=user_profile, course=latest_course)
            messages.success(request, f'Tài khoản của bạn đã được kích hoạt! Bạn đã được ghi danh vào khóa học "{latest_course.title}".')
        except Course.DoesNotExist:
            messages.success(request, 'Tài khoản của bạn đã được kích hoạt!')
        except UserProfile.DoesNotExist:
            messages.warning(request, 'Tài khoản của bạn đã được kích hoạt, nhưng đã có lỗi xảy ra khi tự động ghi danh vào khóa học.')

        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)
        return redirect('progress')
    else:
        return render(request, 'auth/activation_invalid.html')

def login_view(request):
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
                    html_content = render_to_string(email_template_name, context)
                    try:
                        send_mail(
                            subject,
                            'Vui lòng làm theo hướng dẫn để đặt lại mật khẩu của bạn.',
                            settings.DEFAULT_FROM_EMAIL,
                            [user.email],
                            fail_silently=False,
                            html_message=html_content
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
    history_key = f'gemini_chat_history_user_{request.user.id}'
    cache.delete(history_key)
    logout(request)
    messages.success(request, 'Bạn đã đăng xuất thành công!')
    return redirect('home')

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
