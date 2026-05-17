from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from .models import UserProfile, Post, Comment, SymbolCategory, Symbol

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(
        required=True, 
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['avatar', 'bio']
        widgets = {
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'avatar': forms.FileInput(attrs={'class': 'form-control-file'}),
        }

class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Translate labels
        self.fields['old_password'].label = "Mật khẩu cũ"
        self.fields['new_password1'].label = "Mật khẩu mới"
        self.fields['new_password2'].label = "Xác nhận mật khẩu mới"

        # Update widgets
        self.fields['old_password'].widget = forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nhập mật khẩu hiện tại của bạn'})
        self.fields['new_password1'].widget = forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nhập mật khẩu mới'})
        self.fields['new_password2'].widget = forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Nhập lại mật khẩu mới để xác nhận'})
        
        # Remove English help text
        self.fields['new_password2'].help_text = None


# --- Blog Forms --- #

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['content', 'image', 'video']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Bạn đang nghĩ gì?'
            }),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'video': forms.FileInput(attrs={'class': 'form-control'}),
        }

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Viết bình luận...'
            })
        }
        labels = {
            'content': ''  # Hide the label
        }

# --- Symbol Library Forms ---

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
