# 知识库管理脚本

统一入口：

```bash
python services/ai-engine/scripts/knowledge_cli.py list
python services/ai-engine/scripts/knowledge_cli.py sources
python services/ai-engine/scripts/knowledge_cli.py fetch
python services/ai-engine/scripts/knowledge_cli.py import
```

默认扫描目录：

```text
services/ai-engine/data/raw
```

来源清单：

```text
services/ai-engine/data/sources/pediatric_authority_sources.json
```

支持导入文件：

- `.pdf`
- `.txt`

补充说明：

- `fetch` 会将官方 `html/htm` 政策正文页自动抽取为 `.txt` 落到 `data/raw`
- 因此中文政府站来源不必强求 PDF，只要是官方正式正文页也可进入导入链路

说明：

- `list`：列出当前可导入的知识源
- `sources`：列出项目维护的权威资料来源清单及采集模式
- `fetch`：按来源清单下载可自动获取的公开资料，并生成本地下载索引
- `import`：调用 `knowledge_import.py` 将知识源切分、Embedding 并写入 Milvus

建议流程：

```bash
python services/ai-engine/scripts/knowledge_cli.py sources
python services/ai-engine/scripts/knowledge_cli.py fetch
python services/ai-engine/scripts/knowledge_cli.py list
python services/ai-engine/scripts/knowledge_cli.py import
```

来源模式说明：

- `auto`：官方公开且有稳定直链，可自动下载
- `manual_review_required`：公开来源，但需要先人工筛选具体页面/PDF，再补充 `directUrl`
- `licensed_manual_only`：教材、会员内容或版权敏感内容，只能人工授权导入
