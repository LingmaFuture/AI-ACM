# AI-ACM

AI-ACM 是一个中文优先的“AI 算法版 LeetCode”MVP：任何已验证用户都可以上传算法资料，让 AI 生成可判题的题目草稿，在自动质量门禁通过后自行发布到公共题库。

项目已经包含两道可直接练习的种子题：从零实现 KNN 分类器、确定性 K-Means 聚类。

## 已实现

- 公开题库、标签/难度/完成状态筛选、做题页和 Monaco Python 编辑器
- 公开样例运行、隐藏用例提交、SSE 实时结果、个人提交历史
- 浮点容差、聚类标签置换、精确标签和 MSE 阈值检查器
- 邮箱注册验证、HTTP-only 会话、个人训练档案与排行榜
- 私有 PDF/DOCX/MD/TXT/PNG/JPG 上传、文本抽取/OCR、AI 结构化出题
- 草稿编辑、参考答案/空实现/典型错解质量门禁、相似题提示、自助发布
- 举报、管理员下架与恢复 API
- PostgreSQL、Redis/Celery、MinIO、Caddy 和隔离判题容器的 Compose 部署

## 本地开发

本地模式默认使用 SQLite、本地私有存储、同步任务和受限子进程，不要求 Docker、Redis 或 AI 密钥。

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -e 'backend[dev]'
cd backend && uvicorn app.main:app --reload
```

另开一个终端：

```bash
cd web
npm install
npm run dev
```

访问 `http://localhost:3000`。开发环境注册响应会提供“立即验证”链接；没有配置 `AI_API_KEY` 时，上传流程使用可重复的 KNN/K-Means 演示生成器。

后端 OpenAPI 文档位于 `http://localhost:8000/docs`。

## 单机 Docker 部署

1. 复制 `.env.example` 为 `.env`，至少替换 `SECRET_KEY`、`POSTGRES_PASSWORD`、`S3_SECRET_KEY`。
2. 公网部署时将 `SITE_ADDRESS` 和 `FRONTEND_URL` 设为实际 HTTPS 域名，并设置 `COOKIE_SECURE=true`。
3. 配置 OpenAI-compatible 的 `AI_API_KEY`、`AI_BASE_URL`、`AI_MODEL`，以及用于邮箱验证的 `SMTP_URL`。
4. 运行：

```bash
docker compose up --build -d
docker compose ps
```

Caddy 自动处理 HTTPS；MinIO 原始资料桶不会对公网暴露。PostgreSQL、Redis、MinIO 和 Caddy 数据均保存到命名卷。

### 判题安全边界

本地子进程模式只用于开发。公开部署必须使用默认的 `JUDGE_MODE=docker`：每次判题启动一次性非 root 容器，关闭网络，使用只读文件系统，移除 Linux capabilities，并限制 CPU、内存、进程数、运行时间与输出量。AST 策略层还会拒绝 import、文件入口和私有属性访问。

挂载 Docker socket 的 worker 等价于拥有宿主机容器管理权限，因此只能运行平台维护的 worker 镜像，不能向用户开放 worker API。规模扩大后应把 judge worker 迁移到独立虚拟机或 gVisor/Kubernetes 节点。

## 验证

```bash
cd backend
pytest

cd ../web
npm run typecheck
npm run build
```

测试覆盖判题策略、K-Means 标签等价、注册登录、种子题提交、资料生成、质量门禁、发布以及私有草稿权限。

## 关键配置

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL；本地默认 SQLite |
| `REDIS_URL` / `SYNC_TASKS` | Celery 队列；本地同步执行 |
| `STORAGE_BACKEND` | `local` 或 `s3`/MinIO |
| `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` | OpenAI-compatible 生成服务 |
| `SMTP_URL` | 邮箱验证，支持 `smtp://` 与 `smtps://` |
| `JUDGE_MODE` / `JUDGE_IMAGE` | 本地子进程或 Docker 判题 |

## 当前边界

MVP 只支持 Python + 预注入 NumPy，不支持 sklearn、PyTorch、GPU、完整模型训练、比赛、讨论区和付费功能。发布后的判题版本不可覆盖；后续修改应创建新的不可变版本。

