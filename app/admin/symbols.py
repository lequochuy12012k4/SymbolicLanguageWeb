from django.contrib import admin
from ..models import SymbolCategory, Symbol

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
