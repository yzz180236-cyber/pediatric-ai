# 智慧儿科 AI Agent 系统

基于大语言模型与多智能体（Multi-Agent）技术的“To C 育儿陪伴 + To B 诊所辅助”双引擎架构系统。该系统旨在填补家长院外护理的知识盲区，并有效降低儿科医生的沟通与基础文书负荷。

## 🛠 技术栈选型

项目采用彻底的前后端及 AI 中枢解耦架构，保证多语言异构生态的高内聚协同：

| 模块 | 技术选型 | 规范与核心优势 |
| :--- | :--- | :--- |
| **前端展现层** | Taro (React) + TypeScript | 一套代码编译至微信小程序及 H5，全量 TS 保证类型安全。 |
| **UI 组件库** | NutUI-React (京东开源) | 专为移动端与小程序设计，提供丰富的医疗表单与业务组件。 |
| **BFF 网关层** | NestJS (Node.js) | 承担 PII 脱敏拦截与跨域 API 代理转发，与前端共享类型契约。 |
| **AI 中枢层** | Python + LangGraph | 状态机驱动，比单纯的 Prompt Chain 更适合处理多轮问诊与槽位填充。 |
| **包管理架构** | pnpm (Workspace) | Monorepo 体系，彻底解决幽灵依赖，加速 CI/CD 流水线。 |

---

## 🚀 本地开发启动指南

项目采用物理隔离架构，联调时需要并发拉起三个核心服务域。

> 注意：根目录 `.env` / `.env.staging` 已废弃，仅保留为迁移阶段参考文件。新增或修改本地运行配置时，请只使用各服务目录下的 `.env`。

### 0. 环境前置要求
- Node.js >= 18.0.0
- Python >= 3.10
- pnpm >= 8.0.0

### 1. 启动 AI 中枢引擎 (占用端口: 8000)
承担全域大模型推理与意图分发。
```bash
pnpm run dev:ai
```

启动前请先准备：
- `services/ai-engine/.env`
- 可参考 `services/ai-engine/.env.example`

### 2. 启动 BFF 代理网关 (占用端口: 3000)
承担安全合规拦截与 HTTP 跨域代理。
```bash
pnpm install
pnpm run dev:bff
```

启动前请先准备：
- `apps/bff/.env`
- 可参考 `apps/bff/.env.example`

### 3. 启动前端展现层 (H5 联调端占用端口: 10086)
```bash
pnpm install
pnpm run dev:frontend
```

启动前请先准备：
- `apps/frontend/.env`
- 可参考 `apps/frontend/.env.example`

默认 H5 开发服务器监听在 `0.0.0.0`，按 Taro 当前输出端口访问即可。

### 4. 配置文件规范

本项目已改为按服务边界分别管理本地配置：

- `apps/bff/.env`
- `services/ai-engine/.env`
- `apps/frontend/.env`

根目录 `.env` / `.env.staging` 已废弃，不再作为默认运行入口。
详见：[docs/config-migration.md](docs/config-migration.md)
变量清单详见：[docs/config-reference.md](docs/config-reference.md)

### 5. Git 与敏感文件约束

在执行 `git init`、`git add` 或推送到 GitHub 前，先确认以下内容不会进入版本库：

- 各服务真实配置文件：`apps/bff/.env`、`apps/frontend/.env`、`services/ai-engine/.env`
- 本地日志与调试输出：`apps/bff/logs/`、`*.log`
- 用户上传内容与影像文件：`services/ai-engine/uploads/`、`services/ai-engine/private_uploads/`
- 本地构建与运行产物：`apps/bff/dist/`、`services/ai-engine/.venv/`、`coverage/`

仓库根目录已配置 `.gitignore` 进行默认拦截，但 `gitignore` 不是安全边界：

- 只保留 `*.env.example` 作为配置模板，不要提交真实密钥、JWT 私钥、数据库密码或第三方 API Key
- 若任何敏感文件曾进入 Git 历史，必须视为泄露并立即轮换对应凭证
- 医疗问诊日志、患儿图片、诊断上下文默认按敏感数据处理，不应公开上传

---

## 🛡 医疗合规与代码红线
1. **PII 脱敏机制**：严禁向大模型及 AI 中枢引擎直传任何包含明文患者隐私（PII）的信息。脱敏与 Hash 替换必须在 BFF 网关层拦截。
2. **强制类型收敛**：跨包的 TypeScript 接口必须维护在 `@pediatric-ai/shared-types` 共享包内。
3. **大模型幻觉风控**：前端渲染任何由大模型生成的护理建议时，必须附带硬编码的**免责声明**。RAG 检索的内容必须透出文献追溯标识。
