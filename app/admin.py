from django.contrib import admin
from .models import (
    SymbolicLanguage, UserProfile, Course, CourseEnrollment, CourseReview, AIModel,
    Symbol, SymbolCategory, Conversation, Message, Post, Chapter, Exercise, Like, Comment,
    AIProvider, APIModel
)

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

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'difficulty', 'duration', 'created_at']
    search_fields = ['title', 'description']
    list_filter = ['category', 'difficulty', 'created_at']
    ordering = ['-created_at']

@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'course', 'get_progress', 'completed', 'enrolled_at']
    search_fields = ['user_profile__user__username', 'course__title']
    list_filter = ['completed', 'course__category']
    ordering = ['-enrolled_at']

    @admin.display(description='Progress')
    def get_progress(self, obj):
        return f"{obj.progress_percentage:.0f}%"

@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'rating', 'created_at']
    search_fields = ['enrollment__user_profile__user__username', 'enrollment__course__title', 'comment']
    ordering = ['-created_at']

@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'file_path', 'is_active', 'uploaded_at')
    list_editable = ('is_active',)
    ordering = ('-is_active', 'name')
    readonly_fields = ('uploaded_at',)

@admin.register(SymbolCategory)
class SymbolCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ('category',)
    search_fields = ('name',)

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sender', 'content', 'timestamp', 'is_read')
    can_delete = False

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('user', 'updated_at', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'updated_at', 'created_at')
    inlines = [MessageInline]

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'conversation_user', 'timestamp', 'is_read')
    list_filter = ('is_read',)
    list_editable = ('is_read',)
    search_fields = ('sender__username', 'content')
    readonly_fields = ('conversation', 'sender', 'content', 'timestamp')

    @admin.display(description='User')
    def conversation_user(self, obj):
        return obj.conversation.user

class APIModelInline(admin.TabularInline):
    model = APIModel
    extra = 1
    fields = ('model_name', 'is_active')

@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_editable = ('is_active',)
    inlines = [APIModelInline]

admin.site.register(Post)
admin.site.register(Comment)
admin.site.register(Like)
admin.site.register(Chapter)
admin.site.register(Exercise)