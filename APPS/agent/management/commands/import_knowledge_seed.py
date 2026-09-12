"""从 docs/knowledge_seed.json 批量导入知识库初始条目。

用法（在项目根目录 F:\\Django\\OAback 下）：
    .venv\\Scripts\\python.exe manage.py import_knowledge_seed
    .venv\\Scripts\\python.exe manage.py import_knowledge_seed --update
    .venv\\Scripts\\python.exe manage.py import_knowledge_seed --force-private

说明：
- 默认按标题判重，已存在的条目跳过（--update 覆盖更新）。
- 非公开条目（is_public=false）未配置 department_ids 时默认跳过，
  避免导入"无人可见"的私有知识；确认部门 id 后重跑，或用 --force-private 强制导入。
- 复用 ingest_source_text()，自动完成正文归一化、summary 提取、分块与向量化索引。
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from APPS.agent.models import AgentKnowledgeSource
from APPS.agent.services import ingest_source_text
from APPS.oaauth.models import OADepartment

DEFAULT_SEED = Path(__file__).resolve().parents[4] / "docs" / "knowledge_seed.json"


class Command(BaseCommand):
    help = "从 docs/knowledge_seed.json 批量导入知识库初始条目（按标题判重，幂等）"

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_SEED), help="seed JSON 路径")
        parser.add_argument("--update", action="store_true", help="标题已存在时覆盖更新")
        parser.add_argument(
            "--force-private",
            action="store_true",
            help="允许导入未指定部门 id 的私有条目（默认跳过）",
        )

    def handle(self, *args, **options):
        seed_path = Path(options["file"])
        if not seed_path.exists():
            raise CommandError(f"找不到 seed 文件：{seed_path}")

        with seed_path.open("r", encoding="utf-8") as fp:
            entries = json.load(fp)

        self.stdout.write(f"共读取 {len(entries)} 条知识条目")
        created = updated = skipped = failed = 0

        for index, entry in enumerate(entries, start=1):
            title = (entry.get("title") or "").strip()
            content = entry.get("content") or ""
            source_type = entry.get("source_type") or "upload"
            is_public = bool(entry.get("is_public", True))
            department_ids = entry.get("department_ids") or []
            metadata = entry.get("metadata") or {}

            if not title or not content.strip():
                self.stdout.write(self.style.WARNING(f"[{index}] 跳过：标题或正文为空"))
                skipped += 1
                continue

            if not is_public and not department_ids and not options["force_private"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{index}] 跳过：{title} 为非公开条目但未配置 department_ids"
                        f"（--force-private 可强制导入）"
                    )
                )
                skipped += 1
                continue

            departments = list(OADepartment.objects.filter(id__in=department_ids)) if department_ids else []
            if department_ids and len(departments) != len(set(department_ids)):
                missing = set(department_ids) - {d.id for d in departments}
                self.stdout.write(
                    self.style.WARNING(f"[{index}] 警告：部门 id {missing} 不存在，仅导入已匹配部门")
                )

            existing = AgentKnowledgeSource.objects.filter(title=title).first()
            if existing and not options["update"]:
                self.stdout.write(self.style.WARNING(f"[{index}] 跳过：{title} 已存在（--update 可覆盖）"))
                skipped += 1
                continue

            try:
                if existing and options["update"]:
                    existing.delete()
                source = ingest_source_text(
                    title=title,
                    content=content,
                    source_type=source_type,
                    departments=departments,
                    is_public=is_public,
                    metadata=metadata,
                )
                if existing and options["update"]:
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f"[{index}] 已更新：{title}（{source_type}）"))
                else:
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"[{index}] 已导入：{title}（{source_type}）"))
                if source.status == "failed":
                    reason = (source.metadata or {}).get("index_error", "")
                    self.stdout.write(
                        self.style.WARNING(f"[{index}] 注意：{title} 已入库但索引失败：{reason}")
                    )
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"[{index}] 失败：{title} → {exc}"))

        self.stdout.write(
            self.style.SUCCESS(f"完成：新增 {created}，更新 {updated}，跳过 {skipped}，失败 {failed}")
        )
