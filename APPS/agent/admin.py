from django.contrib import admin

from .models import (
    AgentConversation,
    AgentFeedback,
    AgentKnowledgeChunk,
    AgentKnowledgeSource,
    AgentMessage,
)


@admin.register(AgentKnowledgeSource)
class AgentKnowledgeSourceAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "source_type", "is_public", "status", "chunk_count", "created_at")
    list_filter = ("source_type", "is_public", "status")
    search_fields = ("title", "content", "external_app", "external_object_id")


@admin.register(AgentKnowledgeChunk)
class AgentKnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "chunk_index", "token_count", "embedding_model")
    search_fields = ("content", "source__title")


class AgentMessageInline(admin.TabularInline):
    model = AgentMessage
    extra = 0
    readonly_fields = ("role", "content", "created_at")


@admin.register(AgentConversation)
class AgentConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "provider", "model_name", "question_count", "updated_at")
    search_fields = ("title", "user__realname", "last_question", "last_answer")
    inlines = [AgentMessageInline]


@admin.register(AgentFeedback)
class AgentFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "message", "user", "score", "created_at")
    search_fields = ("comment", "user__realname")
