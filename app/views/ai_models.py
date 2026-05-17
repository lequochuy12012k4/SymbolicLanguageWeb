import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.views.decorators.http import require_POST

from app.models import AIModel

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
                fs = FileSystemStorage() # Defaults to MEDIA_ROOT
                
                # Delete old file
                if instance_to_save.pk and instance_to_save.file_path:
                    if fs.exists(instance_to_save.file_path):
                        try:
                            fs.delete(instance_to_save.file_path)
                        except Exception as e:
                            print(f"Could not delete old model file: {e}")

                # Save new file to 'ai_models' subdirectory within MEDIA_ROOT
                filename = fs.save(os.path.join('Models', model_file.name), model_file)
                instance_to_save.file_path = filename

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
