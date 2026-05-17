from django.contrib import admin
from ..models import AIModel, APIModel, AIProvider

@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'file_path', 'is_active', 'uploaded_at')
    list_editable = ('is_active',)
    ordering = ('-is_active', 'name')
    readonly_fields = ('uploaded_at',)

class APIModelInline(admin.TabularInline):
    model = APIModel
    extra = 1
    fields = ('model_name', 'is_active')

@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_editable = ('is_active',)
    inlines = [APIModelInline]
