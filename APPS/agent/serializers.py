from rest_framework import serializers

from APPS.oaauth.models import OADepartment

from .models import (
    AgentConversation,
    AgentFeedback,
    AgentKnowledgeChunk,
    AgentKnowledgeSource,
    AgentMessage,
)


class DepartmentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = OADepartment
        fields = ("id", "name")


class AgentKnowledgeChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentKnowledgeChunk
        fields = (
            "id",
            "chunk_index",
            "content",
            "token_count",
            "embedding_model",
            "content_hash",
            "created_at",
        )


class AgentKnowledgeSourceSerializer(serializers.ModelSerializer):
    department_names = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    source_type_label = serializers.CharField(source="get_source_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    file_url = serializers.SerializerMethodField()
    content_preview = serializers.SerializerMethodField()

    class Meta:
        model = AgentKnowledgeSource
        fields = (
            "id",
            "title",
            "source_type",
            "source_type_label",
            "content_preview",
            "summary",
            "file_url",
            "external_app",
            "external_object_id",
            "author_name",
            "department_names",
            "is_public",
            "metadata",
            "status",
            "status_label",
            "chunk_count",
            "indexed_at",
            "created_at",
            "updated_at",
        )

    def get_department_names(self, obj):
        return [department.name for department in obj.departments.all()]

    def get_author_name(self, obj):
        return obj.author.realname if obj.author_id else ""

    def get_file_url(self, obj):
        return obj.file.url if obj.file else ""

    def get_content_preview(self, obj):
        content = obj.content or obj.summary or ""
        return content[:500]


class AgentKnowledgeUploadSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    file = serializers.FileField(required=False, allow_null=True)
    content = serializers.CharField(required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False, default=True)
    department_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    metadata = serializers.JSONField(required=False, default=dict)


class AgentQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)
    conversation_id = serializers.IntegerField(required=False)
    source_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=20)
    # 前端“联网搜索”开关：true=强制联网，false=禁用联网，不传=走 .env 配置
    web_search = serializers.BooleanField(required=False)


class AgentFeedbackSerializer(serializers.Serializer):
    conversation_id = serializers.IntegerField()
    message_id = serializers.IntegerField(required=False)
    score = serializers.IntegerField(min_value=-1, max_value=1)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class AgentSourceActionSerializer(serializers.Serializer):
    source_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )
    # true=仅重建失败状态的知识源（忽略 source_ids）
    failed_only = serializers.BooleanField(required=False)


class AgentMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMessage
        fields = ("id", "role", "content", "citations", "metadata", "created_at")


class AgentConversationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentConversation
        fields = (
            "id",
            "title",
            "provider",
            "model_name",
            "question_count",
            "last_question",
            "last_answer",
            "created_at",
            "updated_at",
        )


class AgentConversationSerializer(serializers.ModelSerializer):
    messages = AgentMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AgentConversation
        fields = (
            "id",
            "title",
            "provider",
            "model_name",
            "question_count",
            "last_question",
            "last_answer",
            "metadata",
            "created_at",
            "updated_at",
            "messages",
        )


class AgentConversationFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentFeedback
        fields = ("id", "conversation", "message", "user", "score", "comment", "created_at")
        read_only_fields = ("user",)
