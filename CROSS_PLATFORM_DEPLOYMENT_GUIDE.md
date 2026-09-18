# PowerAuto.ai 跨端开发部署技术白皮书

> **版本**: v1.0  
> **更新日期**: 2026-09-18  
> **目标读者**: Mac 端接手人员 / Windows 端协作者  
> **仓库**: `github.com/alexchuang19760730/powerauto.ai`（网站）+ `cgcengine0907`（推理引擎）

---

## 目录

1. [架构总览](#1-架构总览)
2. [账号与密钥清单](#2-账号与密钥清单)
3. [PowerAuto.ai 网站（GitHub Pages）](#3-powerautoai-网站github-pages)
4. [Cloudflare Worker（HF 代理）](#4-cloudflare-workerhf-代理)
5. [Mac M4 推理服务（本地）](#5-mac-m4-推理服务本地)
6. [HF Space 部署](#6-hf-space-部署)
7. [Windows 本地推理部署](#7-windows-本地推理部署)
8. [模型市场与 Playground 运维](#8-模型市场与-playground-运维)
9. [Cloud GPU 付费部署（预留）](#9-cloud-gpu-付费部署预留)
10. [常见问题排查](#10-常见问题排查)
11. [文件清单与目录结构](#11-文件清单与目录结构)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                │
│  https://powerauto.ai/playground/                               │
└──────────────┬──────────────────────────┬───────────────────────┘
               │ ☁️ 云端免费               │ 💻 本地服务
               ▼                          ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│ Cloudflare Worker    │    │ Mac M4 / Windows 本地 llama-server│
│ (HF Inference Proxy) │    │ http://192.168.101.90:8080/v1     │
│ → HF Serverless API  │    │ OpenAI-compatible /v1/chat/...   │
└──────────────────────┘    └──────────────────────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│ HuggingFace 免费推理  │    │ Qwen3.6-35B-A3B-MTP (IQ3_XXS)   │
│ Qwen3-0.6B ~ 8B      │    │ Ornith-1.5-35B-A3B (IQ3_XXS)    │
│ Llama-3.1-8B 等       │    │ Nail-denseIQ4X (生产级)          │
└──────────────────────┘    └──────────────────────────────────┘
```

### 三层推理路径

| 路径 | 端点 | 模型 | 延迟 | 成本 |
|------|------|------|------|------|
| **☁️ HF 免费** | Cloudflare Worker → HF API | Qwen3-0.6B~8B | 200-800ms | 免费 |
| **💻 Mac 本地** | `192.168.101.90:8080` | Qwen3.6-35B MTP | 30-80ms | 免费 |
| **💻 Windows 本地** | `localhost:8080` | Qwen3.6-35B MTP | 30-80ms | 免费 |

---

## 2. 账号与密钥清单

### 密钥管理：私有仓库 + 本地缓存

所有密钥存在 GitHub 私有仓库 `alexchuang19760730/powerauto-secrets`（仅你有权限）。

**Mac 端获取密钥（一步到位）：**

```bash
# 1. Clone 私有仓库（用你的 GitHub PAT 认证）
git clone https://github.com/alexchuang19760730/powerauto-secrets.git ~/.powerauto

# 2. 设置环境变量（加到 ~/.zshrc 或 ~/.bashrc）
export POWERAUTO_GITHUB_PAT="ghp_你的token"
export POWERAUTO_HF_TOKEN="hf_你的token"
export POWERAUTO_CF_TOKEN="cfut_你的token"
export POWERAUTO_CF_ACCOUNT_ID="fb57aa397c138de403429f86ca5e2f24`

# 3. 验证
python3 secrets_manager.py
```

**密钥清单（不存明文，只存变量名）：**

| 变量名 | 用途 | 在哪里使用 |
|--------|------|-----------|
| `POWERAUTO_GITHUB_PAT` | GitHub 仓库 push | `git push` / GitHub API 上传 |
| `POWERAUTO_HF_TOKEN` | HuggingFace 推理 | Cloudflare Worker Secret |
| `POWERAUTO_CF_TOKEN` | Cloudflare Worker 部署 | Worker API 更新 |
| `POWERAUTO_CF_ACCOUNT_ID` | Cloudflare Account | Worker API 路由 |

### Mac 端需要的账号

| 服务 | 需要做什么 |
|------|-----------|
| **GitHub** | 能 push `cgcengine0907` 仓库的 `demo/sweet-spot-windows-fix` 分支 |
| **HuggingFace** | 能创建/管理 Space + 上传 GGUF 模型 |
| **Cloudflare** | 能管理 Worker（目前 Worker 由 Windows 端部署，Mac 端可接手） |

---

## 3. PowerAuto.ai 网站（GitHub Pages）

### 3.1 仓库信息

| 项目 | 值 |
|------|-----|
| **仓库** | `github.com/alexchuang19760730/powerauto.ai` |
| **默认分支** | `main` |
| **部署方式** | GitHub Pages（静态站点） |
| **自定义域名** | `powerauto.ai`（CNAME 已配置） |
| **访问地址** | https://powerauto.ai |

### 3.2 网站结构

```
powerauto.ai (main 分支)
├── index.html                    → 首页（PowerAuto 平台介绍）
├── models/
│   ├── index.html                → 模型市场（12 个模型卡片）
│   └── detail.html               → 模型详情页（参数/下载/API）
├── playground/
│   └── index.html                → Chat Playground（云端+本地推理）
├── installer/
│   ├── PowerAuto-Installer.bat   → Windows 安装检查脚本
│   ├── download-model.bat        → 一键下载模型
│   ├── start-server.bat          → 一键启动 llama-server
│   ├── edge_server.py            → OpenAI 兼容包装器
│   └── README.md                 → 安装说明
├── .htaccess                     → Apache URL 重写
├── CNAME                         → 自定义域名
├── netlify.toml                  → Netlify 配置（备用部署）
├── robots.txt / sitemap.xml      → SEO
├── config.php / admin/           → 后台管理（PHP）
└── index.php                     → PHP 入口
```

### 3.3 更新网站的流程

#### 方法 A：GitHub API 直接上传（推荐，VPN 不通时用）

```bash
# 环境变量
GITHUB_TOKEN="<YOUR_GITHUB_PAT>"
REPO="alexchuang19760730/powerauto.ai"
BRANCH="main"

# 上传单个文件
python3 << 'EOF'
import requests, json, base64, os

TOKEN = "<YOUR_GITHUB_PAT>"
REPO = "alexchuang19760730/powerauto.ai"
BRANCH = "main"
HEADERS = {"Authorization": f"token {TOKEN}"}

def upload_file(local_path, repo_path):
    """上传文件到 GitHub"""
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    
    # 获取现有文件的 SHA（如果存在）
    sha = None
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{repo_path}?ref={BRANCH}", headers=HEADERS)
    if r.status_code == 200:
        sha = r.json().get("sha")
    
    data = {"message": f"Update {repo_path}", "content": content, "branch": BRANCH}
    if sha:
        data["sha"] = sha
    
    r = requests.put(f"https://api.github.com/repos/{REPO}/contents/{repo_path}", 
                     headers=HEADERS, json=data)
    print(f"  {repo_path}: {r.status_code}")
    return r.status_code == 200

# 示例：更新 playground
upload_file("playground/index.html", "playground/index.html")
EOF
```

#### 方法 B：Git push（VPN 通时用）

```bash
cd /path/to/powerauto_deploy
git add .
git commit -m "Update description"
git push origin main
```

### 3.4 更新后验证

```bash
# GitHub Pages 有缓存，更新后需要等待 1-2 分钟
# 或在 URL 后加 ?v=timestamp 强制刷新
curl -s https://powerauto.ai/models/ | head -5
curl -s https://powerauto.ai/playground/ | head -5
```

---

## 4. Cloudflare Worker（HF 代理）

### 4.1 作用

浏览器直接调用 HuggingFace API 会遇到 CORS 问题。Cloudflare Worker 作为中间代理：
- 接收浏览器请求（OpenAI 格式）
- 添加 HF Token（服务端 secret）
- 转发到 HF Serverless Inference API
- 返回结果给浏览器

### 4.2 Worker 信息

| 项目 | 值 |
|------|-----|
| **Worker 名称** | `powerauto-inference` |
| **Worker URL** | `https://powerauto-inference.powerauto-ai.workers.dev` |
| **Account ID** | `fb57aa397c138de403429f86ca5e2f24` |
| **Secret** | `HF_TOKEN` = `<YOUR_HF_TOKEN>` |

### 4.3 更新 Worker 代码

```bash
# 获取最新代码位置
WORKER_CODE="/d/alex/flashkv0516/cgcengine_full/powerauto-platform/cloud-deploy/worker_esm.js"

# 通过 API 更新
ACCOUNT_ID="fb57aa397c138de403429f86ca5e2f24"
CF_TOKEN="<YOUR_CF_TOKEN>"

curl -X PUT "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/powerauto-inference" \
  -H "Authorization: Bearer ${CF_TOKEN}" \
  -H "Content-Type: application/javascript" \
  --data-binary @${WORKER_CODE}
```

### 4.4 Worker 代码（ES Module 格式）

```javascript
// worker_esm.js — Cloudflare Worker: HF Inference Proxy
// Secret: HF_TOKEN (bound via metadata)

export default {
  async fetch(request, env) {
    // CORS 预检
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
        },
      });
    }

    // Health check
    if (request.method === 'GET') {
      return new Response(JSON.stringify({ ok: true, service: 'powerauto-inference-proxy' }), {
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      });
    }

    try {
      const body = await request.json();
      const model = body.model || 'Qwen/Qwen3-1.7B';
      const messages = body.messages || [{ role: 'user', content: 'Hello' }];
      const max_tokens = body.max_tokens || 512;
      const temperature = body.temperature ?? 0.7;
      const stream = body.stream ?? false;

      const hfResp = await fetch('https://api-inference.huggingface.co/models/' + model, {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + env.HF_TOKEN,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ messages, max_tokens, temperature, stream }),
      });

      const respHeaders = new Response(hfResp.headers);
      respHeaders.set('Access-Control-Allow-Origin', '*');
      return new Response(hfResp.body, { status: hfResp.status, headers: respHeaders });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 500,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
      });
    }
  },
};
```

### 4.5 测试 Worker

```bash
# Health check
curl -s "https://powerauto-inference.powerauto-ai.workers.dev"
# → {"ok":true,"service":"powerauto-inference-proxy"}

# 推理测试
curl -s -X POST "https://powerauto-inference.powerauto-ai.workers.dev" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-1.7B",
    "messages": [{"role": "user", "content": "Say hello in one word"}],
    "max_tokens": 16
  }'
```

---

## 5. Mac M4 推理服务（本地）

### 5.1 服务信息

| 项目 | 值 |
|------|-----|
| **仓库** | `github.com/alexchuang19760730/cgcengine0907` |
| **分支** | `demo/sweet-spot-windows-fix` |
| **服务端口** | 8080（OpenAI 兼容）/ 1234-1240（CGC 协议） |
| **模型** | Nail-Qwen3.6-35B-A3B-MTP-UD-IQ3_XXS-denseIQ4X.gguf |
| **Binary** | `llama-server`（常驻进程，非一次性 CLI） |
| **性能目标** | 25+ tok/s（MTP 投机解码） |

### 5.2 启动服务

```bash
cd /Users/alexchuang/Documents/flashkv0516

# 方式 A：使用 run_n30cache.sh（推荐，生产级）
./scripts/run_n30cache.sh \
  -m qwen36 \
  --mtp 3 \
  --dense-iq4x \
  --server-api

# 方式 B：手动启动 llama-server
./src/llama.cpp/build/bin/llama-server \
  --model models/gguf/Nail-Qwen3.6-35B-A3B-MTP-UD-IQ3_XXS-denseIQ4X.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --ctx-size 8192 \
  --n-gpu-layers 99 \
  --spec-type draft-mtp \
  --mtp 3 \
  --chat-template chatml
```

### 5.3 关键环境变量

```bash
# Expert Cache 优化
export CGC_EXPERT_CACHE_BYTES=4294967296    # 4GB expert cache
export LLAMA_EXPERT_CACHE_ALLOW_NGL=1       # 允许 GPU offload + cache
export LLAMA_EXPERT_CACHE_L4_SKIP_LAYER0=1  # 跳过 layer 0

# OA 异步模式（+12.6% speed）
export OA_ASYNC=1

# 防护参数
export CGC_NO_PREFETCH=1
export CGC_VERIFY_DECODE=1
export CGC_DRAFT_DECODE=1
```

### 5.4 验证服务

```bash
# Health
curl -s http://192.168.101.90:8080/health

# Models
curl -s http://192.168.101.90:8080/v1/models

# Chat（测试品质）
curl -s -X POST http://192.168.101.90:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local",
    "messages": [{"role": "user", "content": "请简短介绍巴黎。"}],
    "max_tokens": 64,
    "temperature": 0
  }'

# 性能指标
curl -s http://192.168.101.90:8080/props | python -m json.tool
curl -s http://192.168.101.90:8080/slots | python -m json.tool
```

### 5.5 Playground 连接测试

用户在 `powerauto.ai/playground/` 中：
1. 选择 **💻 本地服务**
2. 输入地址：`http://192.168.101.90:8080`
3. 点击 **连接**
4. 发送消息测试

### 5.6 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| **Chat template 未对齐** | ⚠️ 待修 | `reasoning_format=none` + `chat_format=Content-only` 导致 `<think>` 标签作为 literal text 输出 |
| **MTP 重复循环** | ⚠️ 待修 | MTP + IQ3_XXS 量化下偶尔出现重复 token 循环 |
| **速度** | ✅ | 12-14 tok/s（MTP accept rate 87-94%） |

---

## 6. HF Space 部署

### 6.1 Space 信息

| 项目 | 值 |
|------|-----|
| **Space** | `Alexchuang/powerauto-inference` |
| **SDK** | Static (HTML) |
| **类型** | 免费（无 GPU） |
| **用途** | 托管 Playground 的另一个入口 |

### 6.2 更新 Space

```bash
# 上传文件到 HF Space
python3 << 'EOF'
from huggingface_hub import HfApi

api = HfApi(token="<YOUR_HF_TOKEN>")

# 上传单个文件
api.upload_file(
    path_or_fileobj="playground/index.html",
    path_in_repo="index.html",
    repo_id="Alexchuang/powerauto-inference",
    repo_type="space",
)

print("Upload complete!")
EOF
```

### 6.3 HF 免费推理模型列表

| 模型 | HF Model ID | 说明 |
|------|-------------|------|
| Qwen3-0.6B | `Qwen/Qwen3-0.6B` | 超轻量 |
| Qwen3-1.7B | `Qwen/Qwen3-1.7B` | 轻量级 |
| Qwen3-4B | `Qwen/Qwen3-4B` | 端侧旗舰 |
| Qwen3-8B | `Qwen/Qwen3-8B` | 中等规模 |
| Llama-3.1-8B | `meta-llama/Llama-3.1-8B-Instruct` | Meta 开源 |
| Gemma-2-9B | `google/gemma-2-9b-it` | Google |
| Phi-3.5-Mini | `microsoft/Phi-3.5-mini-instruct` | 代码能力强 |
| Zephyr-7B | `HuggingFaceH4/zephyr-7b-beta` | 对话流畅 |

### 6.4 HF 模型仓库

| 仓库 | 用途 |
|------|------|
| `Alexchuang/cgcengine-models` | 所有 GGUF 模型文件（含 Ornith-1.5） |
| `Alexchuang/powerauto-inference` | HF Space（Playground 静态部署） |

---

## 7. Windows 本地推理部署

### 7.1 用户使用流程

```
1. 下载 D:\alex\powerauto_deploy\installer\ 目录
2. 运行 download-model.bat → 选择模型（Qwen3 / Ornith）
3. 运行 start-server.bat → 服务启动在 localhost:8080
4. 打开 https://powerauto.ai/playground/
5. 选择 💻 本地服务 → 输入 http://localhost:8080
6. 点击连接 → 开始对话
```

### 7.2 start-server.bat 核心逻辑

```batch
REM 自动检测 GPU
nvidia-smi >nul 2>&1
if %errorlevel%==0 (
    set NGL=99
) else (
    set NGL=0
)

REM 启动 llama-server
llama-server.exe ^
    --model models\Nail-Qwen3.6-35B-A3B-MTP-UD-IQ3_XXS-denseIQ4X.gguf ^
    --host 0.0.0.0 ^
    --port 8080 ^
    --n-gpu-layers %NGL% ^
    --ctx-size 4096 ^
    --spec-type draft-mtp ^
    --chat-template chatml
```

### 7.3 边缘计算模式（CGC 协议）

`edge_server.py` 提供 CGC 协议端点：
- `GET /v1/cgc/health` — 健康检查
- `GET /v1/cgc/profile` — 硬件配置
- `POST /v1/cgc/emit` — Prefill 探针
- `POST /v1/cgc/resume` — Token 流（SSE）

---

## 8. 模型市场与 Playground 运维

### 8.1 添加新模型到市场

编辑 `powerauto_deploy/models/index.html`，在模型卡片区域添加：

```html
<div class="model-card" onclick="window.location.href='detail.html?id=模型ID'">
  <div class="model-badge">免费</div>
  <h3>模型名称</h3>
  <p class="model-desc">模型描述</p>
  <div class="model-stats">
    <span>📊 参数量</span>
    <span>⚡ 速度</span>
  </div>
</div>
```

### 8.2 Playground 配置

编辑 `powerauto_deploy/playground/index.html`，修改云端模型列表：

```javascript
const CLOUD_MODELS = [
  { id: "Qwen/Qwen3-0.6B", name: "Qwen3-0.6B", desc: "超轻量", speed: "~50 tok/s" },
  { id: "Qwen/Qwen3-1.7B", name: "Qwen3-1.7B", desc: "轻量级", speed: "~40 tok/s" },
  // ... 更多模型
];
```

### 8.3 连接 Mac 服务

Playground 中的 `connectToServer()` 函数：

```javascript
async function connectToServer() {
  const url = document.getElementById('serverUrl').value;
  // 验证 health
  const resp = await fetch(url.replace('/v1', '') + '/health');
  // 或直接用 /v1/models
  const models = await fetch(url + '/v1/models');
  // 连接成功 → 显示聊天界面
}
```

---

## 9. Cloud GPU 付费部署（预留）

### 9.1 方案对比

| 平台 | 价格 | GPU | 适合模型 | 说明 |
|------|------|-----|----------|------|
| **Vast.ai** | $0.2-0.5/hr | RTX 4090/A6000 | 35B GGUF | 最便宜 |
| **RunPod** | $0.4-0.8/hr | A100/H100 | 35B GGUF | UX 好 |
| **Modal** | $0.001/s 起 | A100 | 35B GGUF | 按秒计费 |
| **Replicate** | 按预测 | 各种 | 自定义 | 一键部署 |

### 9.2 部署步骤（以 Vast.ai 为例）

```bash
# 1. 租一台 RTX 4090 ($0.3/hr)
# 2. SSH 连接
ssh root@<vast-ip>

# 3. 安装 llama.cpp
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && make -j

# 4. 下载模型
pip install huggingface_hub
huggingface-cli download Alexchuang/cgcengine-models \
  Nail-Qwen3.6-35B-A3B-MTP-UD-IQ3_XXS-denseIQ4X.gguf \
  --local-dir models/

# 5. 启动服务
./llama-server \
  --model models/Nail-Qwen3.6-35B-A3B-MTP-UD-IQ3_XXS-denseIQ4X.gguf \
  --host 0.0.0.0 \
  --port 8080 \
  --n-gpu-layers 99 \
  --spec-type draft-mtp

# 6. Playground 连接
# 输入 http://<vast-ip>:8080
```

---

## 10. 常见问题排查

### 10.1 Playground "Failed to fetch"

| 原因 | 解决 |
|------|------|
| Cloudflare Worker 未激活 | 检查 `https://powerauto-inference.powerauto-ai.workers.dev` |
| HF API 超时 | 模型可能冷启动，等待 10-30 秒 |
| CORS 错误 | 确认 Worker 代码正确（含 `Access-Control-Allow-Origin: *`） |

### 10.2 Mac 服务连不上

```bash
# 检查 Mac 防火墙
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --listapps

# 检查端口监听
lsof -i :8080

# 检查服务进程
ps aux | grep llama-server
```

### 10.3 Chat 品质退化（输出 <think> 标签）

**原因**: `reasoning_format=none` + `chat_format=Content-only`  
**修复**: 在 Mac 端启动时添加 `--chat-template chatml` 或使用 `run_n30cache.sh` 脚本

### 10.4 MTP 重复循环

**原因**: MTP + IQ3_XXS 量化下 draft model 过于激进  
**修复**: 降低 MTP 数量 `--mtp 1` 或禁用 MTP

---

## 11. 文件清单与目录结构

### 11.1 本地文件（Windows 端）

```
D:\alex\
├── flashkv0516\
│   └── cgcengine_full\           ← 主开发仓库
│       ├── agent_harness\         ← Agent 框架（6 阶段）
│       │   ├── harness/
│       │   ├── memory/            ← 学习记忆（从 demo 分支合并）
│       │   ├── skills/            ← 技能库
│       │   └── engine_loop/       ← 闭环蒸馏引擎
│       ├── src/fusion_route/      ← SmartRouter（规则判定）
│       └── powerauto-platform\    ← 网站源码
│           ├── models/            ← 模型市场页面
│           ├── playground/        ← Chat Playground
│           ├── installer/         ← Windows 安装包
│           └── cloud-deploy/      ← Cloudflare Worker + HF 部署
├── powerauto_deploy\              ← GitHub Pages 仓库（main 分支）
│   ├── index.html                 ← 首页
│   ├── models/                    ← 模型市场
│   ├── playground/                ← Playground
│   └── installer/                 ← Windows 安装包
└── cgcengine0907\                 ← Mac 端仓库（待 clone）
```

### 11.2 Mac 端需要 clone 的仓库

```bash
# 1. 主开发仓库
git clone https://github.com/alexchuang19760730/cgcengine0907.git
cd cgcengine0907
git checkout demo/sweet-spot-windows-fix

# 2. 网站仓库（可选，如需修改网页）
git clone https://github.com/alexchuang19760730/powerauto.ai.git
```

### 11.3 关键文件速查

| 文件 | 位置 | 用途 |
|------|------|------|
| `run_n30cache.sh` | `cgcengine0907/scripts/` | Mac 启动推理服务 |
| `edge_server.py` | `powerauto-platform/installer/` | Windows OpenAI 兼容包装 |
| `worker_esm.js` | `powerauto-platform/cloud-deploy/` | Cloudflare Worker 代码 |
| `playground/index.html` | `powerauto_deploy/playground/` | Chat 界面 |
| `models/index.html` | `powerauto_deploy/models/` | 模型市场页面 |
| `memory/*.md` | `cgcengine0907/agent_harness/memory/` | 学习记忆日志 |

---

## 附录 A：Mac 端接手清单

Mac 端需要完成的工作：

### 必做

1. **Clone 仓库**
   ```bash
   git clone https://github.com/alexchuang19760730/cgcengine0907.git
   git checkout demo/sweet-spot-windows-fix
   ```

2. **启动推理服务（修复 chat template）**
   ```bash
   ./scripts/run_n30cache.sh -m qwen36 --mtp 3 --dense-iq4x --server-api
   ```
   - 确认 `/health` 返回正确
   - 确认 `/v1/models` 列出模型
   - 确认 chat 品质正常（无 <think> 标签泄漏）

3. **测试 Playground 连接**
   - 打开 `powerauto.ai/playground/`
   - 选择 💻 本地服务
   - 输入 `http://192.168.101.90:8080`
   - 发送测试消息

4. **更新 HF 模型仓库**
   ```bash
   from huggingface_hub import HfApi
   api = HfApi(token="hf_...")
   api.upload_folder(folder_path="models/gguf/", repo_id="Alexchuang/cgcengine-models")
   ```

### 可选

5. **部署 Cloudflare Worker**（如需更新代码）
6. **优化 MTP + 量化参数**（目标 25+ tok/s）
7. **部署 Cloud GPU**（如需公网推理服务）

---

## 附录 B：环境变量速查

### Mac 端

```bash
# Expert Cache
CGC_EXPERT_CACHE_BYTES=4294967296
LLAMA_EXPERT_CACHE_ALLOW_NGL=1
LLAMA_EXPERT_CACHE_L4_SKIP_LAYER0=1

# OA 异步
OA_ASYNC=1

# 防护
CGC_NO_PREFETCH=1
CGC_VERIFY_DECODE=1
CGC_DRAFT_DECODE=1
```

### Cloudflare Worker

```bash
# Secret（在 Dashboard 设置）
HF_TOKEN=<YOUR_HF_TOKEN>
```

### Windows

```bash
# llama-server 启动参数
--model models\Nail-Qwen3.6-35B-A3B-MTP-UD-IQ3_XXS-denseIQ4X.gguf
--host 0.0.0.0
--port 8080
--n-gpu-layers 99
--spec-type draft-mtp
--chat-template chatml
```

---

## 附录 C：2026-09-18 实测更新（端侧包装器 v2 ＋ Portal ＋ 四个平台事实）

> 本节由**端云侧部署管理**这条线追加；上面 §1–§11 与附录 A／B 的原文**一字未改**。
> `powerauto-secrets` 里那份白皮书副本仍是改动前的版本（未同步，见 C.6）。

### C.1 `installer/edge_server.py` v2 —— 修掉 6 个会在真实部署时爆掉或**静默出错**的问题

| # | v1 的问题 | 症状 | v2 |
|---|---|---|---|
| 1 | `./llama-server` 写死 | PATH 里明明有（Homebrew／系统套件）也用不到 | 依序找：`--llama-server` → 脚本同目录 → `bin/` → CWD → PATH |
| 2 | 找不到执行档／模型直接抛 traceback | 用户看到堆栈，而不是「该把档案放哪」 | 印出**找过哪些路径**并 rc=1 |
| 3 | `os.sysconf` 在 Windows 不存在 | Windows 端打 `/v1/cgc/profile` 会 AttributeError（而 Windows 是目标平台） | 加 Windows fallback（`GlobalMemoryStatusEx`） |
| 4 | `0.0.0.0` ＋ CORS `*` ＋ 无认证 | 同网段任何人可用你的 GPU | 加 `--api-key`；**绑非 loopback 又没设 key 时主动出声** |
| 5 | 没有 OPTIONS handler | 浏览器带 `X-API-Key` 时 preflight 失败，Playground 连不上 | 加 `do_OPTIONS`（含 `Allow-Headers`） |
| 6 | **手写 ChatML** | 对 Qwen 刚好正确，对其他模型**静默**给错 prompt（没有错误讯息，只有品质变差） | 预设委派 llama-server 自己的 `/v1/chat/completions`（套 GGUF 内建 chat template），失败才回退，并在 status 说明走哪条 |

新增：

- `GET /v1/edge/status` —— 管理面事实一次说清楚（worker 可达吗、走哪条 chat 路由、host 规格、llama-server 路径）。
  ★ 其中 `chat_probe`（**能力**，启动时用 worker 的 `/v1/models` 推断）与 `chat_route`（**上次实际走过**的路由）
  **刻意分成两个字段**：「它能」与「它这次走了」不是同一件事。
- `--self-test` —— **36 格**黑箱自测（用 stub worker，**不需要真模型**），含 SSE、认证、attach、降级、旗标探测、失败讯息不得是 traceback。
- 新旗标：`--llama-server`、`--worker-url`（接既有 worker）、`--no-worker`（只开管理面，**降级不是挂掉**）、
  `--api-key`、`--endpoint-id`、`--chat-format auto|native|chatml`、`--log-dir`。

### C.2 Portal 上线：`portal/`

超级使用者登入后要看的那一页（端云侧部署管理视图）。用法与设计见 `portal/README.md`，要点：

- **角色接入点只有一个字段**：`window.POWERAUTO_ROLE ∈ {superuser, admin, user}`（或 `?role=`）。
  ★ **预设是最小权限 `user`** —— 这一页部署后任何人都能开，预设给 `superuser` 等于「忘了接闸门就自动全开」。
- 分区：`superuser` 全看；`admin` 看端点／目标／机队；`user` 只看端点切换；
  **未设定或乱填 ⇒ 视为 `user`**。
- ★ **这一层是显示，不是闸门。** HTML 谁都能抓，真正的闸门必须在服务器端。
- 数据是 CGC repo 的 `fleet_export.json` **快照**，本页**只转述、不重算**任何指标
  （动能、七日、目标绑定只有在 CGC repo 算得出来；两份实作必然漂移，而漂移是静默的）。

### C.3 ★ 四个实测的平台／网络事实（会改架构）

| 事实 | 量测 | 后果 |
|---|---|---|
| **`*.workers.dev` 从中国大陆不可达** | `powerauto-inference.powerauto-ai.workers.dev` 的 DNS 解到 `118.184.26.113`（中国 IP，**不是** Cloudflare 的 104.x／172.x），TLS 前就 timeout；**同一颗沙箱**的 `example.com`／`www.cloudflare.com`／`powerauto.ai` 都 HTTP 200 | 是 **DNS 污染**，不是 Worker 挂了 ⇒ 云侧 endpoint **必须挂自定义域名** |
| **Cloudflare 帐号里 `zones = 0`** | `GET /zones?account.id=...` 回 **0 笔**；Worker routes API 回 `Authentication error` | 这个帐号**没有任何域名** ⇒ **`api.powerauto.ai` 现在挂不起来**（要先把域名加进 Cloudflare、再去注册商改 NS） |
| **`huggingface.co` 从这台机器不可达** | `--noproxy '*'` 也 HTTP 000；curl 曾试图连 `31.13.83.34`（**Meta 的 IP**） | HF token **无法在本机验证**；模型下载得靠别的通道（**这正是 Worker 存在的理由**） |
| **`powerauto.ai` 在 GitHub Pages** | 解到 `185.199.108.153` | 站是**静态**的 ⇒ repo 里的 `admin/index.php`（PHP session）**在那个宿主上不会执行**（只会被当纯文本下载）。`.htaccess` 自述的「GoDaddy / Apache」是**另一套**宿主，两者并存 |

**推论（重要）**：**闸门不能靠 PHP。** 要做「只有某种角色才看得到」的服务器端闸门，
只能用 Cloudflare（Worker 验签／Access）——见 `portal/README.md`。

### C.4 ★ 实测抓到的一个观察器缺陷：可達 ≠ 是我們的服務

同一次实测里发现：port 8080 上当时是 **CGC fork 的 `llama-server`**
（`/v1/cgc/profile` 回 404，因为那是 PowerAuto 的扩充端点），
而 Portal 的探测**只看可达性** ⇒ 它会对**别人的**服务报 **LIVE**。
症状**完全像「一切正常」**，是最贵的一种。

已修：edge 端点的探测加**身分断言**（探 `/v1/edge/status`，比对 `object` 与 `endpoint_id`），新增两个状态：

| 状态 | 意义 |
|---|---|
| `foreign` | 可达，但那个埠上的东西**不是我们的**（HTTP 4xx 或 `object` 不符，或 `endpoint_id` 认错机器） |
| `unverified` | 可达，但身分**验不了**（探测途中网路错）—— 不假装 LIVE |

`portal/serve.py --self-test` **16/16**，含一个「假装是别人服务」的 fixture
（没有它，这条最像正常的故障永远测不到）。

### C.5 端侧「真模型 → 真推理」这一步：**未完成，需要窗口**

包装器已用 stub worker 黑箱验证 **36/36**，但**真模型这一步本身没做**，原因是**资源冲突，不是程式问题**：

- 2026-09-18 14:14 实测：**port 8080 被 CGC fork 的 llama-server 占用**
  （pid 82118，RSS **8.2 GB**，`--expert-cache 8 GB`），机器 `PhysMem 15G used / 10G wired / **158M unused**`。
- 按这台机器既有的铁律（动手前先看 listener 与量测行程，任一非空就停手），
  **没有**起 PowerAuto 的 edge server —— 会增记忆体压力，可能扰动另一条线正在跑的量测。

补上时（窗口空出来，已备好一颗 637.8 MB 的真模型 `~/Documents/powerauto-models/tinyllama.gguf`）：

```bash
python3 installer/edge_server.py \
  --model ~/Documents/powerauto-models/tinyllama.gguf \
  --llama-server "$(command -v llama-server)" \
  --host 127.0.0.1 --port 8080 --endpoint-id edge-local --log-dir .

# 另开一个终端
python3 portal/serve.py --port 8787
# 浏览器开 http://127.0.0.1:8787/ ，按「全部探测」⇒ edge-local 应变 LIVE
```

### C.6 已知的未同步项

`powerauto-secrets` 里的 `CROSS_PLATFORM_DEPLOYMENT_GUIDE.md` 是**本节追加之前**的版本
（24,208 B）。两边内容会漂移，而且漂移是静默的 —— 待决定：同步，或把那份副本移除。

---

*文档结束。如需更新，请联系 powerauto.ai 团队。*
