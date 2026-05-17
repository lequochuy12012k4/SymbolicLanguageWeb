from django.contrib import admin
from ..models import SymbolicLanguage, UserProfile

@admin.register(SymbolicLanguage)
class SymbolicLanguageAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_at']
    search_fields = ['title', 'description']
    list_filter = ['created_at']
    ordering = ['-created_at']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_manager']
    search_fields = ['user__username']
    list_filter = ['is_manager']
