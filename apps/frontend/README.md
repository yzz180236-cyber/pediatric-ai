# Frontend

本服务本地开发只读取：

- `apps/frontend/.env`

模板文件：

- `apps/frontend/.env.example`

## 允许出现的变量

前端仅允许放公开变量，必须以 `TARO_APP_` 开头。

当前最小配置：

- `TARO_APP_BFF_URL`
- `TARO_APP_AI_ENGINE_URL`

## 本地启动

```bash
cd apps/frontend
pnpm run dev:h5
```
