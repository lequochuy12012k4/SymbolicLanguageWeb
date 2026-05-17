from django import forms
from ..models import SymbolCategory, Symbol

class SymbolCategoryForm(forms.ModelForm):
    class Meta:
        model = SymbolCategory
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên danh mục'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Mô tả ngắn về danh mục'}),
        }
        labels = {
            'name': 'Tên danh mục',
            'description': 'Mô tả',
        }

class SymbolForm(forms.ModelForm):
    class Meta:
        model = Symbol
        fields = ['category', 'name', 'description', 'image', 'video']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tên ký hiệu'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Giải thích chi tiết về ký hiệu'}),
            'image': forms.FileInput(attrs={'class': 'form-control-file'}),
            'video': forms.FileInput(attrs={'class': 'form-control-file'}),
        }
        labels = {
            'category': 'Danh mục',
            'name': 'Tên ký hiệu',
            'description': 'Mô tả chi tiết',
            'image': 'Ảnh minh họa',
            'video': 'Video hướng dẫn',
        }
