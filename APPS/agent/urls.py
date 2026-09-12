from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views


app_name = "agent"

router = DefaultRouter(trailing_slash=False)
router.register("sources", views.AgentSourceViewSet, basename="agent-source")
router.register("conversations", views.AgentConversationViewSet, basename="agent-conversation")

urlpatterns = [
    path("config", views.AgentConfigView.as_view(), name="agent_config"),
    path("ask", views.AgentAskView.as_view(), name="agent_ask"),
    path("ask/stream", views.AgentAskStreamView.as_view(), name="agent_ask_stream"),
    path("upload", views.AgentUploadView.as_view(), name="agent_upload"),
    path("sync/informs", views.AgentSyncInformView.as_view(), name="agent_sync_informs"),
    path("reindex", views.AgentReindexView.as_view(), name="agent_reindex"),
    path("sources/batch-delete", views.AgentSourceBatchDeleteView.as_view(), name="agent_source_batch_delete"),
    path("feedback", views.AgentFeedbackView.as_view(), name="agent_feedback"),
    path("stats", views.AgentStatsView.as_view(), name="agent_stats"),
] + router.urls
