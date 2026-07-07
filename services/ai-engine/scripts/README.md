# 知识库管理脚本

统一入口：

```bash
python services/ai-engine/scripts/knowledge_cli.py list
python services/ai-engine/scripts/knowledge_cli.py import
```

默认扫描目录：

```text
services/ai-engine/data/raw
```

支持导入文件：

- `.pdf`
- `.txt`

说明：

- `list`：列出当前可导入的知识源
- `import`：调用 `knowledge_import.py` 将知识源切分、Embedding 并写入 Milvus
