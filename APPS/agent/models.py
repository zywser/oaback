from django.db import models

from APPS.oaauth.models import OADepartment, OAUser


class AgentSourceType(models.TextChoices):
    INFORM = "inform", "Notice"
    UPLOAD = "upload", "Upload"
    MANUAL = "manual", "Manual"
    FAQ = "faq", "FAQ"


class AgentSourceStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    INDEXED = "indexed", "Indexed"
    FAILED = "failed", "Failed"


class AgentConversationRole(models.TextChoices):
    SYSTEM = "system", "System"
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class AgentKnowledgeSource(models.Model):
    title = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=AgentSourceType.choices, default=AgentSourceType.MANUAL)
    content = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    file = models.FileField(upload_to="agent/knowledge/", null=True, blank=True)
    external_app = models.CharField(max_length=80, blank=True, null=True)
    external_object_id = models.CharField(max_length=80, blank=True, null=True)
    author = models.ForeignKey(
        OAUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_sources",
        related_query_name="agent_source",
    )
    departments = models.ManyToManyField(OADepartment, blank=True, related_name="agent_sources")
    is_public = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=AgentSourceStatus.choices, default=AgentSourceStatus.PENDING)
    chunk_count = models.PositiveIntegerField(default=0)
    indexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["source_type", "status"]),
            models.Index(fields=["external_app", "external_object_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["external_app", "external_object_id"],
                name="uniq_agent_source_origin",
            )
        ]

    def __str__(self):
        return self.title


class AgentKnowledgeChunk(models.Model):
    source = models.ForeignKey(
        AgentKnowledgeSource,
        on_delete=models.CASCADE,
        related_name="chunks",
        related_query_name="chunk",
    )
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    embedding = models.JSONField(default=list, blank=True)
    embedding_model = models.CharField(max_length=100, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("source_id", "chunk_index")
        constraints = [
            models.UniqueConstraint(fields=["source", "chunk_index"], name="uniq_agent_chunk_order")
        ]

    def __str__(self):
        return f"{self.source_id}#{self.chunk_index}"


class AgentConversation(models.Model):
    user = models.ForeignKey(
        OAUser,
        on_delete=models.CASCADE,
        related_name="agent_conversations",
        related_query_name="agent_conversation",
    )
    title = models.CharField(max_length=200, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    question_count = models.PositiveIntegerField(default=0)
    last_question = models.TextField(blank=True)
    last_answer = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return self.title or f"Conversation {self.pk}"


class AgentMessage(models.Model):
    conversation = models.ForeignKey(
        AgentConversation,
        on_delete=models.CASCADE,
        related_name="messages",
        related_query_name="message",
    )
    role = models.CharField(max_length=20, choices=AgentConversationRole.choices)
    content = models.TextField()
    citations = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class AgentFeedback(models.Model):
    conversation = models.ForeignKey(
        AgentConversation,
        on_delete=models.CASCADE,
        related_name="feedbacks",
        related_query_name="feedback",
    )
    message = models.ForeignKey(
        AgentMessage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="feedbacks",
        related_query_name="feedback",
    )
    user = models.ForeignKey(OAUser, on_delete=models.CASCADE, related_name="agent_feedbacks")
    score = models.SmallIntegerField(default=1)
    comment = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
