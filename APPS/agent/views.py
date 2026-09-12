import json

from django.db.models import Q
from django.http import StreamingHttpResponse
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from APPS.oaauth.models import OADepartment

from .models import AgentConversation, AgentFeedback, AgentKnowledgeSource, AgentMessage
from .serializers import (
    AgentConversationFeedbackSerializer,
    AgentConversationListSerializer,
    AgentConversationSerializer,
    AgentFeedbackSerializer,
    AgentKnowledgeSourceSerializer,
    AgentKnowledgeUploadSerializer,
    AgentQuestionSerializer,
    AgentSourceActionSerializer,
)
from .services import (
    AgentServiceError,
    accessible_sources_queryset,
    ask_question,
    create_feedback,
    ingest_source_text,
    get_config_snapshot,
    is_boarder,
    purge_source_vectors,
    rebuild_source_index,
    stream_ask_question,
    sync_inform_sources,
)


def _sse_encode(event_stream):
    """把事件 dict 流封装为 SSE（text/event-stream）文本流。"""
    for event in event_stream:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class AgentSourceViewSet(viewsets.ModelViewSet):
    serializer_class = AgentKnowledgeSourceSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get_queryset(self):
        queryset = accessible_sources_queryset(self.request.user).select_related("author").prefetch_related("departments")
        search = self.request.query_params.get("search", "").strip()
        source_type = self.request.query_params.get("source_type", "").strip()
        status_value = self.request.query_params.get("status", "").strip()

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(content__icontains=search)
                | Q(summary__icontains=search)
                | Q(external_app__icontains=search)
                | Q(external_object_id__icontains=search)
            )
        if source_type:
            queryset = queryset.filter(source_type=source_type)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset.order_by("-created_at")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        purge_source_vectors(instance)
        if instance.file:
            instance.file.delete(save=False)
        return super().destroy(request, *args, **kwargs)


class AgentConversationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get_queryset(self):
        return (
            AgentConversation.objects.filter(user=self.request.user)
            .prefetch_related("messages")
            .order_by("-updated_at")
        )

    def get_serializer_class(self):
        if self.action == "list":
            return AgentConversationListSerializer
        return AgentConversationSerializer


class AgentConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        snapshot = get_config_snapshot()
        snapshot.update(
            {
                "boarder": is_boarder(request.user),
                "source_count": accessible_sources_queryset(request.user).count(),
                "conversation_count": AgentConversation.objects.filter(user=request.user).count(),
            }
        )
        return Response(snapshot)


class AgentAskView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conversation = None
        conversation_id = serializer.validated_data.get("conversation_id")
        if conversation_id:
            conversation = AgentConversation.objects.filter(user=request.user, id=conversation_id).first()
            if conversation is None:
                return Response({"detail": "会话不存在或无权访问"}, status=status.HTTP_404_NOT_FOUND)

        try:
            payload = ask_question(
                request.user,
                serializer.validated_data["question"],
                conversation=conversation,
                source_ids=serializer.validated_data.get("source_ids"),
                top_k=serializer.validated_data.get("top_k"),
                web_search=serializer.validated_data.get("web_search"),
            )
        except AgentServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        assistant_message = payload["assistant_message"]
        return Response(
            {
                "conversation": AgentConversationSerializer(payload["conversation"]).data,
                "answer": assistant_message.content,
                "message_id": assistant_message.id,
                "sources": payload["references"],
                "usage": payload["usage"],
            }
        )


class AgentAskStreamView(APIView):
    """对话问答的流式版本：POST /agent/ask/stream，返回 SSE 事件流。

    事件格式（每行 ``data: {json}\\n\\n``）：
      start: 会话与消息已落库，含 conversation_id / message_id / references
      delta: 回答内容增量，前端逐块追加即可
      usage: token 用量（若服务端返回）
      done:  流结束，含完整 answer / sources / usage
      error: 出错信息
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conversation = None
        conversation_id = serializer.validated_data.get("conversation_id")
        if conversation_id:
            conversation = AgentConversation.objects.filter(user=request.user, id=conversation_id).first()
            if conversation is None:
                return Response({"detail": "会话不存在或无权访问"}, status=status.HTTP_404_NOT_FOUND)

        try:
            event_stream = stream_ask_question(
                request.user,
                serializer.validated_data["question"],
                conversation=conversation,
                source_ids=serializer.validated_data.get("source_ids"),
                top_k=serializer.validated_data.get("top_k"),
                web_search=serializer.validated_data.get("web_search"),
            )
        except AgentServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = StreamingHttpResponse(_sse_encode(event_stream), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class AgentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentKnowledgeUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        department_ids = serializer.validated_data.get("department_ids") or []
        metadata = serializer.validated_data.get("metadata") or {}
        file_obj = serializer.validated_data.get("file")
        title = serializer.validated_data.get("title") or (
            file_obj.name.rsplit(".", 1)[0] if file_obj else "知识源"
        )
        try:
            source = ingest_source_text(
                title=title,
                content=serializer.validated_data.get("content", ""),
                source_type="upload",
                author=request.user,
                departments=OADepartment.objects.filter(id__in=department_ids) if department_ids else [],
                is_public=serializer.validated_data.get("is_public", True),
                external_app=None,
                external_object_id=None,
                file=file_obj,
                metadata=metadata,
            )
        except AgentServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AgentKnowledgeSourceSerializer(source).data, status=status.HTTP_201_CREATED)


class AgentSyncInformView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            sources = sync_inform_sources()
        except AgentServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "同步完成", "count": len(sources)})


class AgentReindexView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentSourceActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source_ids = serializer.validated_data.get("source_ids") or []
        failed_only = serializer.validated_data.get("failed_only") or False
        queryset = accessible_sources_queryset(request.user)
        if failed_only:
            queryset = queryset.filter(status="failed")
        elif source_ids:
            queryset = queryset.filter(id__in=source_ids)
        sources = list(queryset)
        success = 0
        failed = []
        for source in sources:
            try:
                rebuild_source_index(source)
                success += 1
            except AgentServiceError:
                failed.append(source.id)
        return Response({"detail": "重建完成", "success": success, "failed": failed})


class AgentSourceBatchDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentSourceActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source_ids = serializer.validated_data.get("source_ids") or []
        if not source_ids:
            return Response({"detail": "请至少选择一个知识源"}, status=400)
        queryset = accessible_sources_queryset(request.user).filter(id__in=source_ids)
        deleted = 0
        for source in queryset:
            purge_source_vectors(source)
            if source.file:
                source.file.delete(save=False)
            source.delete()
            deleted += 1
        return Response({"detail": f"已删除 {deleted} 个知识源", "deleted": deleted})


class AgentFeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AgentFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = AgentConversation.objects.filter(user=request.user, id=serializer.validated_data["conversation_id"]).first()
        if conversation is None:
            return Response({"detail": "会话不存在或无权访问"}, status=status.HTTP_404_NOT_FOUND)

        message = None
        message_id = serializer.validated_data.get("message_id")
        if message_id:
            message = AgentMessage.objects.filter(conversation=conversation, id=message_id).first()

        feedback = create_feedback(
            conversation=conversation,
            user=request.user,
            score=serializer.validated_data["score"],
            comment=serializer.validated_data.get("comment", ""),
            message=message,
        )
        return Response(AgentConversationFeedbackSerializer(feedback).data, status=status.HTTP_201_CREATED)


class AgentStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        source_qs = accessible_sources_queryset(request.user)
        return Response(
            {
                "source_count": source_qs.count(),
                "chunk_count": sum(source_qs.values_list("chunk_count", flat=True)),
                "conversation_count": AgentConversation.objects.filter(user=request.user).count(),
                "feedback_count": AgentFeedback.objects.filter(user=request.user).count(),
                "indexed_source_count": source_qs.filter(status="indexed").count(),
                "failed_source_count": source_qs.filter(status="failed").count(),
            }
        )
