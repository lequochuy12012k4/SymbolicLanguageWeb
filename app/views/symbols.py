from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app.models import SymbolCategory, Symbol
from app.forms import SymbolCategoryForm, SymbolForm
from .utils import predict_from_video_file

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
