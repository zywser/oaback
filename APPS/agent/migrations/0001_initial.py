# Generated manually for the agent app.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("oaauth", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentKnowledgeSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                (
                    "source_type",
                    models.CharField(
                        choices=[("inform", "Notice"), ("upload", "Upload"), ("manual", "Manual"), ("faq", "FAQ")],
                        default="manual",
                        max_length=20,
                    ),
                ),
                ("content", models.TextField(blank=True)),
                ("summary", models.TextField(blank=True)),
                ("file", models.FileField(blank=True, null=True, upload_to="agent/knowledge/")),
                ("external_app", models.CharField(blank=True, max_length=80, null=True)),
                ("external_object_id", models.CharField(blank=True, max_length=80, null=True)),
                ("is_public", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("indexed", "Indexed"), ("failed", "Failed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("chunk_count", models.PositiveIntegerField(default=0)),
                ("indexed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="agent_sources",
                        related_query_name="agent_source",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.CreateModel(
            name="AgentConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, max_length=200)),
                ("provider", models.CharField(blank=True, max_length=50)),
                ("model_name", models.CharField(blank=True, max_length=100)),
                ("question_count", models.PositiveIntegerField(default=0)),
                ("last_question", models.TextField(blank=True)),
                ("last_answer", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_conversations",
                        related_query_name="agent_conversation",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at",),
            },
        ),
        migrations.CreateModel(
            name="AgentKnowledgeChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("embedding", models.JSONField(blank=True, default=list)),
                ("embedding_model", models.CharField(blank=True, max_length=100)),
                ("content_hash", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        related_query_name="chunk",
                        to="agent.agentknowledgesource",
                    ),
                ),
            ],
            options={
                "ordering": ("source_id", "chunk_index"),
            },
        ),
        migrations.CreateModel(
            name="AgentMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[("system", "System"), ("user", "User"), ("assistant", "Assistant")],
                        max_length=20,
                    ),
                ),
                ("content", models.TextField()),
                ("citations", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        related_query_name="message",
                        to="agent.agentconversation",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at",),
            },
        ),
        migrations.CreateModel(
            name="AgentFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("score", models.SmallIntegerField(default=1)),
                ("comment", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedbacks",
                        related_query_name="feedback",
                        to="agent.agentconversation",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feedbacks",
                        related_query_name="feedback",
                        to="agent.agentmessage",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_feedbacks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddField(
            model_name="agentknowledgesource",
            name="departments",
            field=models.ManyToManyField(blank=True, related_name="agent_sources", to="oaauth.oadepartment"),
        ),
        migrations.AddConstraint(
            model_name="agentknowledgesource",
            constraint=models.UniqueConstraint(
                fields=("external_app", "external_object_id"),
                name="uniq_agent_source_origin",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentknowledgechunk",
            constraint=models.UniqueConstraint(
                fields=("source", "chunk_index"),
                name="uniq_agent_chunk_order",
            ),
        ),
        migrations.AddIndex(
            model_name="agentknowledgesource",
            index=models.Index(fields=["source_type", "status"], name="agent_sourc_source_t_3f6e1d_idx"),
        ),
        migrations.AddIndex(
            model_name="agentknowledgesource",
            index=models.Index(fields=["external_app", "external_object_id"], name="agent_sourc_external_3cf21f_idx"),
        ),
    ]
