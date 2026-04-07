# Fitbit Dify App - 项目交接文档

**项目名称**: Fitbit 数据智能分析系统  
**最后更新**: 2026年4月8日  
**项目状态**: ✅ 生产就绪

---

## 📋 快速导航

1. [项目概述](#项目概述)
2. [系统架构](#系统架构)
3. [快速启动](#快速启动)
4. [核心功能](#核心功能)
5. [部署指南](#部署指南)
6. [数据导入](#数据导入)
7. [API 接口](#api-接口)
8. [文件结构](#文件结构)
9. [常见问题](#常见问题)
10. [下一步工作](#下一步工作)

---

## 项目概述

### 项目目标

本项目是一个 **Fitbit 数据智能分析系统**，提供以下核心功能：

- ✅ **数据导入**: 支持 Fitbit 导出数据（CSV 格式）的多用户导入
- ✅ **特征提取**: 自动计算心率、步数、活动、睡眠等指标
- ✅ **机器学习预测**: 疲劳度预测（低/中/高）
- ✅ **AI 解释**: 通过 Dify AI 平台提供个性化健康分析和建议
- ✅ **两级分析**: 支持小时级和日级两种时间粒度的分析

### 最新功能（2026年4月）

#### Hour Level 分析（小时级）
- 分析单个小时的用户行为数据
- 不涉及基线对比，关注当前实时状态
- 由前端第三列的"分析这一段"触发

#### Day Level 分析（日级）
- 聚合全天（24小时）的数据
- 自动与用户长期基线对比
- 提供步数、活动、睡眠等指标的差异分析
- 由前端第二列的"📅 分析此日期"按钮触发
- **核心修复**: 日级分析现在使用当天汇总数据（而非单个小时数据）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Web 前端 (Dashboard)                      │
│  • 用户选择 (Column 1)                                       │
│  • 日期/时间线 (Column 2) → 📅 分析此日期（日级）           │
│  • 小时级分析 (Column 3) → 分析这一段（小时级）             │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP/JSON REST API
┌─────────────────────▼───────────────────────────────────────┐
│                    后端 API (FastAPI)                        │
│  • /api/v1/users/ - 用户管理                                 │
│  • /api/v1/segments/ - 数据段管理和分析                      │
│  • /api/v1/profiles/ - 用户画像和基线                        │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
┌───────▼──────┐ ┌───▼─────┐ ┌────▼──────────┐
│  SQLite DB   │ │  Dify   │ │  ML Predictor │
│  (本地存储)   │ │  AI     │ │  (疲劳预测)    │
└──────────────┘ └─────────┘ └───────────────┘
```

### 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| **后端框架** | FastAPI | 0.104+ |
| **数据库** | SQLite | 3.x |
| **ORM** | SQLAlchemy | 2.0+ |
| **前端** | HTML5 + Vanilla JS | - |
| **AI 集成** | Dify Workflow API | - |
| **数据处理** | Pandas | 2.0+ |

---

## 快速启动

### 前置要求

- Python 3.10+
- Dify 账户及 API 密钥（用于 AI 分析）
- Fitbit 导出数据（CSV 格式）

### 1. 环境设置

```bash
cd backend
python -m venv .venv

# macOS/Linux
source .venv/bin/activate

# Windows
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入必要的配置：

```env
# Dify 配置
DIFY_API_URL=https://api.dify.ai/v1
DIFY_API_KEY=your_dify_api_key
DIFY_WORKFLOW_ID=your_workflow_id

# 应用配置
DATABASE_URL=sqlite:///./app.db
DEBUG=False
```

### 3. 启动服务

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4. 访问应用

- **Web Dashboard**: http://127.0.0.1:8000
- **API 文档**: http://127.0.0.1:8000/docs
- **API Schema**: http://127.0.0.1:8000/openapi.json

---

## 核心功能

### 数据导入流程

```bash
python backend/scripts/import_fitbit_export.py \
  --external-user-id user123 \
  --name "Alice" \
  --export-dir data/raw/fitbit-export/export_folder
```

**重要**: 确保导出目录包含以下 CSV 文件：
- `dailyActivity_merged.csv`
- `heartrate_seconds_merged.csv`
- `minuteStepsNarrow_merged.csv`
- 其他可选的 Fitbit 指标文件

### 小时级分析（Hour Level）

**触发方式**: 前端第三列，选择时间线小时 → 点击"分析这一段"

**数据范围**: 单个小时的数据
- 步数（单小时）
- 心率（该小时平均值）
- 活动强度
- 久坐时间

**Dify 提示**: 不包含基线对比，关注当前指标的评价

**示例响应**:
```json
{
  "segment_id": "xxx",
  "analysis_type": "hour_level",
  "llm_output": {
    "summary": "该小时活动充分，心率正常",
    "explanation": "步数131步，低于小时平均...",
    "personalized_advice": "..."
  }
}
```

### 日级分析（Day Level）

**触发方式**: 前端第二列，加载日期时间线 → 点击"📅 分析此日期"

**数据范围**: 当天全部24小时的汇总数据
- **总步数**（当天总计，如 7891 步）
- **总热量**（当天总计）
- **总活动分钟数**（全天）
- **总睡眠分钟数**（全天）
- **平均心率**（全天平均）

**对比分析**: 与用户长期基线对比
- 步数对比（当天 vs 平均）
- 活动对比（当天 vs 平均）
- 睡眠对比（当天 vs 平均）

**Dify 提示**: 包含用户目标、基线数据，明确指示进行基线对比

**示例响应**:
```json
{
  "segment_id": "xxx",
  "analysis_type": "day_level",
  "daily_comparison": {
    "total_steps": 7891,
    "baseline_steps": 6163.61,
    "steps_ratio": 1.28,  // 与基线比较：128%
    "comparison": {...}
  },
  "llm_output": {
    "summary": "今天表现出色，步数和活动量均超过长期平均水平",
    "explanation": "...",
    "personalized_advice": "..."
  }
}
```

---

## 部署指南

### 生产环境部署

#### 1. 使用 Gunicorn（推荐）

```bash
cd backend
pip install gunicorn
gunicorn \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  app.main:app
```

#### 2. 使用 Docker

创建 `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建并运行：
```bash
docker build -t fitbit-dify:latest .
docker run -d -p 8000:8000 \
  -e DIFY_API_KEY=xxx \
  -e DIFY_WORKFLOW_ID=xxx \
  -v $(pwd)/data:/app/data \
  fitbit-dify:latest
```

#### 3. 性能优化

- 启用数据库连接池（SQLAlchemy `pool_size`, `max_overflow`）
- 配置 Nginx 反向代理和缓存
- 使用 Redis 缓存用户画像数据
- 定期清理过期的分析结果

### 数据库备份

```bash
# SQLite 备份
cp backend/app.db backups/app_$(date +%Y%m%d_%H%M%S).db

# 定期备份脚本（每日）
0 2 * * * cp /path/to/app.db /backups/app_$(date +\%Y\%m\%d).db
```

---

## 数据导入

### 从 Fitbit 导出数据

1. 在 Fitbit 应用中：Settings → Download Your Data
2. 提供您的邮箱地址，Fitbit 会发送下载链接
3. 下载 ZIP 文件并解压到 `data/raw/fitbit-export/`

### 导入方式

#### 方式 1: 使用脚本导入

```bash
python backend/scripts/import_fitbit_export.py \
  --external-user-id user123 \
  --name "Alice" \
  --export-dir data/raw/fitbit-export/fitabase_export_folder
```

#### 方式 2: 使用 API 导入

```bash
curl -X POST http://127.0.0.1:8000/api/v1/segments/import \
  -H "Content-Type: application/json" \
  -d '{
    "external_user_id": "user123",
    "name": "Alice",
    "data_source": "fitbit",
    "export_path": "data/raw/fitbit-export/..."
  }'
```

### 导入验证

```bash
# 查看导入的用户
curl http://127.0.0.1:8000/api/v1/users | python -m json.tool

# 查看某用户的 segments
curl http://127.0.0.1:8000/api/v1/users/{user_id}/timeline | python -m json.tool
```

---

## API 接口

### 用户管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/users` | 获取所有用户 |
| GET | `/api/v1/users/{user_id}` | 获取用户详情 |
| GET | `/api/v1/users/{user_id}/profile` | 获取用户画像和基线 |

### 数据段管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/users/{user_id}/timeline` | 获取用户时间线（分页） |
| GET | `/api/v1/segments/{segment_id}` | 获取 segment 详情 |
| POST | `/api/v1/segments/{segment_id}/analyze` | 分析某个 segment |

### 分析接口详解

**Request**:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/segments/{segment_id}/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "分析这段时间的健康状态",
    "analysis_type": "hour_level"
  }'
```

**Parameters**:
- `user_query` (string): 用户的自定义查询问题
- `analysis_type` (string, optional): `"hour_level"` 或 `"day_level"`，默认 `"hour_level"`

**Response**:
```json
{
  "segment_id": "xxx",
  "user_id": "yyy",
  "analysis_type": "hour_level",
  "status": "sent",
  "dify_payload": { ... },
  "llm_output": {
    "summary": "...",
    "explanation": "...",
    "personalized_advice": "..."
  },
  "daily_comparison": null  // 仅 day_level 包含
}
```

---

## 文件结构

```
fitbit-dify-app-main/
├── README.md                          # 基础快速启动指南
├── PROJECT_HANDOVER.md               # ⭐ 本文档（项目交接文档）
├── .env.example                       # 环境变量模板
├── .gitignore                         # Git 配置
│
├── backend/
│   ├── requirements.txt               # Python 依赖
│   ├── .env                          # 🔒 环境变量（凭证，不上传）
│   ├── app.db                        # SQLite 数据库
│   │
│   ├── app/
│   │   ├── main.py                   # FastAPI 应用入口
│   │   ├── api/
│   │   │   ├── router.py             # 路由定义
│   │   │   └── routes/
│   │   │       ├── users.py          # 用户端点
│   │   │       └── segments.py       # segment 端点
│   │   │
│   │   ├── models/                   # SQLAlchemy 数据模型
│   │   │   ├── user.py
│   │   │   ├── raw_segment.py
│   │   │   ├── dify_run.py
│   │   │   ├── model_prediction.py
│   │   │   └── ...
│   │   │
│   │   ├── services/                 # 业务逻辑层
│   │   │   ├── analysis_service.py   # ⭐ 两级分析核心逻辑
│   │   │   ├── daily_analysis_service.py  # ⭐ 日级数据聚合
│   │   │   ├── feature_service.py    # 特征提取
│   │   │   ├── prediction_service.py # 疲劳预测
│   │   │   └── ...
│   │   │
│   │   ├── dify/
│   │   │   ├── client.py             # Dify API 客户端
│   │   │   └── prompt_builder.py     # ⭐ 提示词构造（hour/day 区分）
│   │   │
│   │   ├── db/
│   │   │   └── session.py            # 数据库会话
│   │   │
│   │   ├── static/
│   │   │   └── dashboard.html        # ⭐ 前端 Web Dashboard
│   │   │
│   │   └── core/
│   │       └── config.py             # 配置管理
│   │
│   ├── scripts/
│   │   ├── import_fitbit_export.py   # 数据导入脚本
│   │   ├── bootstrap_fitabase_profiles.py
│   │   ├── backfill_features_predictions.py
│   │   └── ...
│   │
│   └── tests/                        # 单元测试
│       └── ...
│
├── data/
│   ├── raw/                          # 原始 Fitbit 导出数据
│   │   └── fitbit-export/
│   └── processed/                    # 处理后的数据
│       └── dify-workflow-blueprint.json
│
└── docs/（已合并至 PROJECT_HANDOVER.md）
```

### 关键文件说明

#### 后端核心文件

| 文件 | 职责 | 最近修改 |
|------|------|---------|
| `app/services/analysis_service.py` | 两级分析调度逻辑 | 2026/04/08 |
| `app/services/daily_analysis_service.py` | 日级数据聚合与对比 | 2026/04/08 |
| `app/dify/prompt_builder.py` | Hour/Day 提示词区分 | 2026/04/08 |
| `app/static/dashboard.html` | 三列布局 UI，Hour/Day 分析按钮 | 2026/04/08 |
| `app/importers/fitbit_export.py` | Fitbit 数据导入 | 早期 |

#### 重要修改（2026年4月）

```python
# analysis_service.py: 日级分析使用聚合数据（而非单小时）
if analysis_type == "day_level":
    daily_aggregate_payload = {
        "steps": daily_data.total_steps,      # 当天总步数
        "calories": daily_data.total_calories,
        "sleep_minutes": daily_data.total_sleep_minutes,
        ...
    }
    dify_payload = build_analysis_payload(..., raw_payload=daily_aggregate_payload)
```

```javascript
// dashboard.html: 移除第三列分析类型选择器，硬编码 hour_level
async function runAnalysis() {
    state.selectedAnalysis = await api(..., {
        analysis_type: "hour_level"  // ⭐ 固定为小时级
    });
}
```

---

## 常见问题

### Q: 如何添加新的分析类型（如周级）？

**A**: 按以下步骤：

1. 创建 `weekly_analysis_service.py`:
```python
def get_weekly_data(db, user_id, segment):
    """聚合周数据"""
    pass

def build_weekly_comparison(weekly_data, baseline):
    """周数据与基线对比"""
    pass
```

2. 在 `analysis_service.py` 中添加条件分支：
```python
if analysis_type == "week_level":
    weekly_data = get_weekly_data(...)
    dify_payload = build_analysis_payload(..., analysis_type="week_level")
```

3. 在 `prompt_builder.py` 中添加周级提示词：
```python
def _build_week_level_prompt(profile_json, goals_json):
    """构建周级分析提示词"""
    return "..."
```

4. 更新前端，添加按钮触发

### Q: 如何修改 Dify 提示词？

**A**: 编辑 `backend/app/dify/prompt_builder.py`:

```python
def _build_hour_level_prompt(profile_json):
    """修改提示词内容"""
    return "你修改后的提示词..."

def _build_day_level_prompt(profile_json, goals_json, baseline_stats):
    """修改提示词内容"""
    return "你修改后的提示词..."
```

### Q: 如何添加新的预测标签（不仅仅是疲劳度）？

**A**: 修改 `backend/app/ml/predictor.py`:

```python
def predict(feature_vector):
    # 现在只返回 fatigue_low/medium/high
    # 改为返回更多标签如：energy_level, sleep_quality, etc.
    pass
```

### Q: 数据库损坏或需要重置？

**A**:
```bash
# 删除旧数据库
rm backend/app.db

# 让 SQLAlchemy 自动创建新数据库
python -m uvicorn app.main:app --reload

# 重新导入数据
python backend/scripts/import_fitbit_export.py ...
```

### Q: 如何调试 Dify 集成问题？

**A**: 查看日志并检查：
```bash
# 检查 Dify 连接
python backend/scripts/check_dify_connection.py

# 验证 API 的完整 payload（在响应中）
curl -X POST http://localhost:8000/api/v1/segments/{id}/analyze \
  -d '{"user_query":"test"}' | python -m json.tool | grep dify_payload
```

---

## 下一步工作

### 已完成 ✅

- ✅ 两级分析功能实现（Hour/Day）
- ✅ 前端 UI 三列布局（用户/日期/片段）
- ✅ 日级分析聚合数据修复
- ✅ 数据清理（自动删除旧分析）
- ✅ API 文档完善

### 建议的改进 🚀

#### 短期（1-2 周）
1. **监控和日志**
   - 添加日志系统（Python logging）
   - 监控 API 响应时间
   - 错误告警机制

2. **用户体验**
   - 缓存用户画像数据（Redis）
   - 优化前端加载速度
   - 添加分析历史（可保存和对比）

3. **测试**
   - 添加单元测试覆盖（pytest）
   - 集成测试（测试完整流程）
   - 性能基准测试

#### 中期（1-3 个月）
1. **功能扩展**
   - 周级/月级分析
   - 多用户对比分析
   - 自定义时间范围分析
   - 趋势预测（ARIMA/Prophet）

2. **数据管理**
   - 数据加密（敏感的 Fitbit 数据）
   - 隐私合规（GDPR/CCPA）
   - 数据导出和迁移

3. **AI 集成**
   - 分析结果缓存（避免重复 Dify 调用）
   - 自定义 Dify 工作流
   - 本地 LLM 备选方案

#### 长期（3+ 个月）
1. **移动应用**
   - React Native/Flutter 应用
   - 推送通知（异常提醒）
   - 离线支持

2. **社交功能**
   - 分享分析结果
   - 与朋友对比
   - 社群挑战

3. **商业化**
   - 订阅模式
   - 高级分析功能
   - API 市场

---

## 联系和支持

### 项目维护

- **Repository**: 本地路径 `/Users/shansizhe/Bioelectronic_Lab/Fitbit/fitbit-dify-app/fitbit-dify-app-main`
- **主要贡献者**: [Your Team]
- **最后活跃**: 2026年4月8日

### 常见命令速查

```bash
# 启动服务
cd backend && source .venv/bin/activate
python -m uvicorn app.main:app --reload

# 导入数据
python scripts/import_fitbit_export.py --external-user-id user1 --name "User 1" --export-dir data/raw/fitbit-export/...

# 测试 API
curl http://localhost:8000/docs

# 数据库操作
sqlite3 app.db "SELECT COUNT(*) FROM raw_segment;"

# 检查依赖
pip list | grep -E "fastapi|sqlalchemy|dify"
```

### 文档继续阅读

- API 详细文档: `/docs/api.md`
- 架构深度分析: `/docs/architecture.md`
- Dify 工作流指南: `/docs/dify-workflow.md`

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 2.0 | 2026/04/08 | 日级分析数据聚合修复，移除分析类型选择器 |
| 1.5 | 2026/04/07 | 两级分析功能完成 |
| 1.0 | 2026/03/15 | 初始版本（单小时级分析） |

---

**准备好接手这个项目了吗？** 祝你成功！🚀
