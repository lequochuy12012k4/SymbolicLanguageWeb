from django.contrib import admin
from ..models import Conversation, Message

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
