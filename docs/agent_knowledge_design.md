# agentAPP 知识库设计方案（手动上传版）

> 依据：`docs/agent_knowledge_base.md`（内容建议稿）
> 范围：知识库内容体系落地 + 手动上传功能设计 + 任意格式文件解析方案
> 日期：2026-09-07

---

## 1. 需求解读

| 诉求 | 含义 | 落点 |
| --- | --- | --- |
| 根据设计稿设计知识库 | 把 12 条知识条目、分类、metadata 结构落地为可导入内容 | `docs/knowledge_seed.json` |
| 手动上传 | 管理员/用户在页面上传文件或手填正文，入库并进入检索 | 上传流程 + 前端页面规划 |
| 文件格式随意 | 上传任意格式文件都能被解析成可检索文本 | 文件解析增强（第 5 节） |

---

## 2. 现状盘点（已核对代码）

后端能力已具备，无需重写，按缺口补齐即可：

| 能力 | 现状 | 说明 |
| --- | --- | --- |
| 数据模型 | ✅ 已就绪 | `AgentKnowledgeSource`（title/source_type/content/file/departments/is_public/metadata/status/chunk_count）|
| 分块向量化 | ✅ 已就绪 | `AgentKnowledgeChunk` + `rebuild_source_index()`，状态机 `pending → indexed / failed` |
| 上传接口 | ✅ 已就绪 | `POST /api/agent/upload`（`AgentUploadView`）|
| 检索问答 | ✅ 已就绪 | `POST /api/agent/ask`，支持 `source_ids` 限定知识源 |
| 文件解析 | ⚠️ 有缺口 | 仅支持 txt/md/log/csv/json/html/xml/docx/xlsx；**PDF、doc、xls、ppt/pptx 会解析失败或乱码** |
| 类型指定 | ⚠️ 有缺口 | 上传接口把 `source_type` 写死为 `upload`，无法按设计稿导入 `manual/faq/inform` 类型 |

两个缺口正好对应"文件格式随意"和"按设计稿导入"，见第 4、5 节。

---

## 3. 内容体系设计（设计稿落地）

设计稿 12 条 → 映射到现有模型字段：

| # | 条目 | source_type | is_public | 可见范围 | metadata.scene | metadata.audience |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | OA系统快速开始 | manual | true | 全员 | 系统入门 | 全体员工 |
| 2 | 登录与密码重置 | faq | true | 全员 | 账号登录 | 全体员工 |
| 3 | 员工新增与激活 | manual | true | 全员 | 员工管理 | 管理员 |
| 4 | 部门管理说明 | manual | true | 全员 | 部门管理 | 全体员工 |
| 5 | 通知发布规范 | faq | true | 全员 | 通知发布 | 全体员工 |
| 6 | 通知阅读与已读规则 | inform | true | 全员 | 通知阅读 | 全体员工 |
| 7 | 请假申请流程 | manual | false | 人事/直属部门 | 请假申请 | 员工 |
| 8 | 请假审批规则 | faq | false | 负责人/审批人 | 请假审批 | 部门负责人 |
| 9 | 首页统计口径 | manual | true | 全员 | 首页统计 | 全体员工 |
| 10 | 图片上传说明 | faq | true | 全员 | 图片上传 | 全体员工 |
| 11 | 智能助手怎么提问 | manual | true | 全员 | 智能助手 | 全体员工 |
| 12 | 知识库维护规范 | manual | false | 管理员 | 知识库维护 | 管理员 |

设计要点（沿用设计稿原则）：
- 每条知识只回答一个明确问题，标题可直接看懂，便于向量检索命中。
- 公开知识（1-6、9-11）与部门知识（7、8、12）分开，避免权限混乱。
- 每条都带 `metadata`：`tags` / `summary` / `audience` / `scene`，导入时由 `ingest_source_text()` 自动把 `summary` 写入摘要字段。
- 第 7、8、12 条 `is_public=false`，导入时需按实际部门 id 填 `department_ids`（seed 中已留占位说明）。

---

## 4. 手动上传功能设计

### 4.1 上传处理流程

```
┌─ 前端页面 ──────────────┐   ┌─ 后端 POST /api/agent/upload ─────────────────────────────┐   ┌─ 检索侧 ───────┐
│ ① 选择文件（任意格式）    │──▶│ ② 保存文件到 media/agent/knowledge/                        │   │ ⑦ 用户提问     │
│ ② 填写标题/可见范围/标签  │   │ ③ 按后缀路由解析器提取正文（第5节）                          │──▶│ ⑧ 向量检索 topK │
│ ③ 提交 multipart/form    │   │ ④ 正文为空 → failed，返回原因；非空 → 继续                    │   │ ⑨ 引用回答     │
│ ④ 展示状态/分块数/重试   │◀──│ ⑤ RecursiveCharacterTextSplitter 分块（900/120）            │   └────────────────┘
└─────────────────────────┘   │ ⑥ 批量 embedding → chunk 落库 → status=indexed            │
                               └──────────────────────────────────────────────────────────┘
```

状态机：`pending`（提交成功）→ `indexed`（分块+向量化成功）→ `failed`（解析失败/嵌入失败，`metadata.index_error` 记录原因）。

### 4.2 格式支持矩阵（增强后）

| 格式 | 现状 | 增强后 | 解析器 |
| --- | --- | --- | --- |
| .txt / .md / .log / .json / .csv | ✅ | ✅ | 原生读取 / csv / json 美化 |
| .html / .htm / .xml | ✅ | ✅ | HTMLParser / 去标签 |
| .docx / .xlsx | ✅ | ✅ | zipfile + XML / sharedStrings |
| **.pdf** | ❌ 乱码 | ✅ | pypdf 逐页提取 |
| **.pptx** | ❌ | ✅ | python-pptx 提取文本 |
| **.xls** | ❌ | ✅ | pandas.read_excel（需 xlrd）|
| **.doc / .ppt（老版）** | ❌ | ⚠️ 提示 | 引导转存 docx/pptx 后重传 |
| 图片/压缩包/音视频 | ❌ | ❌ 明确拒绝 | 提示"无法解析为文本" |

> 兜底策略：未知后缀先按 UTF-8 尝试读取；若含大量不可打印字符（乱码），判定为二进制不可解析 → `failed` 并返回原因，不静默入库垃圾内容。

### 4.3 接口协议（增强点）

现有 `AgentUploadView` 两处增强：

1. `AgentKnowledgeUploadSerializer` 增加 `source_type` 字段（choices 校验），默认 `upload`：
   ```python
   source_type = serializers.ChoiceField(
       choices=["upload", "manual", "faq", "inform"], required=False, default="upload"
   )
   ```
2. `AgentUploadView` 中把写死的 `source_type="upload"` 改为 `serializer.validated_data.get("source_type", "upload")`。

这样 `knowledge_seed.json` 可按设计稿指定 `manual/faq/inform` 类型导入。

请求体（multipart/form-data）：
```
title: 请假申请流程
file: <file>            # 可选，与 content 二选一
content: "……"          # 可选，手填正文
source_type: manual      # upload/manual/faq/inform
is_public: false
department_ids: [2, 5]   # 非公开时指定可见部门
metadata: {"tags": ["请假"], "scene": "请假申请", "audience": ["员工"]}
```

### 4.4 权限模型（沿用现有）

| 对象 | 可见规则 |
| --- | --- |
| is_public=true | 全员可见 |
| is_public=false | 仅 `departments` 指定部门可见 |
| author（上传者） | 自己的私有知识始终可见 |
| 董事会（boarder） | 全部可见（含私有） |

### 4.5 前端页面规划（Vue3，独立工程）

建议新增「知识库管理」页，四个区域：

1. **上传区**：拖拽/选择文件 + 标题输入 + 可见范围（全员/指定部门多选）+ 标签输入 + 提交按钮；上传中显示进度，完成后显示 `status` 徽标（待索引/已索引/失败）与 `chunk_count`。
2. **知识源列表**：表格列 = 标题 / 类型 / 状态 / 分块数 / 可见范围 / 作者 / 更新时间；支持 `search`、`source_type`、`status` 筛选（后端已支持）。
3. **操作列**：删除（后端已连带删除文件）、重建索引（`POST /reindex`）、查看正文预览。
4. **统计卡片**：调用 `GET /stats` 展示知识源数、分块数、已索引/失败数、会话数。

---

## 5. 文件解析增强（关键实现）

`APPS/agent/services.py` 的 `extract_text_from_file()` 增加三个分支 + 二进制兜底：

```python
# requirements.txt 新增：pypdf、python-pptx、xlrd

def _text_from_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return normalize_text("\n\n".join(pages))

def _text_from_pptx(path: Path) -> str:
    from pptx import Presentation
    prs = Presentation(str(path))
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                parts.append(shape.text)
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append("\t".join(cells))
    return normalize_text("\n\n".join(parts))

def _is_binary_garbage(text: str) -> bool:
    """启发式判定：不可打印字符占比过高视为二进制乱码"""
    if not text:
        return True
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
    return printable / len(text) < 0.8

def extract_text_from_file(path: str | Path) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    # ... 原有 txt/md/csv/json/html/xml/docx/xlsx 分支保持不变 ...
    if suffix == ".pdf":
        return _text_from_pdf(file_path)
    if suffix == ".pptx":
        return _text_from_pptx(file_path)
    if suffix in {".xls", ".xlsm"}:
        import pandas as pd
        frames = pd.read_excel(file_path, sheet_name=None, dtype=str)
        rows = []
        for frame in frames.values():
            rows.append(frame.fillna("").astype(str).agg("\t".join, axis=1).str.cat(sep="\n"))
        return normalize_text("\n\n".join(rows))
    if suffix in {".doc", ".ppt"}:
        raise AgentServiceError(f"暂不支持旧版 {suffix} 格式，请另存为 docx/pptx 后重传")

    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    if _is_binary_garbage(raw):
        raise AgentServiceError(f"无法解析该文件格式（{suffix or '未知后缀'}），请上传文本类文档")
    return normalize_text(raw)
```

要点：
- 新增分支放在原 `raw = read_text(...)` 之前，避免二进制文件先被乱码读取。
- 失败统一抛 `AgentServiceError`，`rebuild_source_index()` 会把状态置为 `failed` 并记录 `index_error`，前端可读原因展示。

---

## 6. 落地步骤

1. `pip install pypdf python-pptx xlrd`（写入 requirements.txt）。
2. 按第 5 节扩展 `services.py`。
3. 按第 4.3 节增强 upload 接口（serializer + view）。
4. 执行 `python manage.py makemigrations agent && python manage.py migrate`（如无模型变更则跳过）。
5. 用 `docs/knowledge_seed.json` 批量导入 12 条初始知识（脚本调 `POST /api/agent/upload`，第 7/8/12 条需先填实际部门 id）。
6. 前端按 4.5 建「知识库管理」页。

---

## 7. 交付物

| 文件 | 说明 |
| --- | --- |
| `docs/agent_knowledge_design.md` | 本设计文档 |
| `docs/knowledge_seed.json` | 12 条可导入知识条目（含 metadata），可直接喂给 upload 接口 |
