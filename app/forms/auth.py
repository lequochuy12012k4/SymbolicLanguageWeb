from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from ..models import UserProfile

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
