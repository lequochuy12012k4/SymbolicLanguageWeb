from django.contrib import admin
from ..models import Course, Chapter, Exercise, CourseEnrollment, CourseReview

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

admin.site.register(Chapter)
admin.site.register(Exercise)
