# PowerAuto Local Inference Engine

本地大模型推理引擎，连接 PowerAuto Playground 在线试用。

## 快速开始

### 1. 安装依赖

```cmd
pip install huggingface_hub
```

### 2. 下载模型

```cmd
download-model.bat
```

选择要下载的模型（Qwen3-4B / Qwen3.6-35B / Ornith-1.5 等）。

### 3. 启动服务

```cmd
start-server.bat
```

服务启动后，在 https://powerauto.ai/playground/ 中输入：

```
http://localhost:8080
```

点击"连接"即可开始对话。

## 手动启动

### 使用 start-server.bat（推荐）

自动检测 GPU、选择模型、配置参数。

### 手动启动 llama-server

```cmd
llama-server.exe -m models\Qwen3.6-35B-A3B.gguf --host 0.0.0.0 --port 8080 -c 8192 -ngl 99
```

### 使用 edge_server.py（高级）

```cmd
python edge_server.py --model models\Qwen3.6-35B-A3B.gguf --port 8080 --ngl 99
```

edge_server.py 额外提供 CGC 协议端点（/v1/cgc/emit, /v1/cgc/resume）。

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/v1/models` | GET | 列出可用模型 |
| `/v1/chat/completions` | POST | OpenAI chat completions |
| `/v1/completions` | POST | OpenAI completions |
| `/health` | GET | 健康检查 |
| `/v1/cgc/emit` | POST | Prefill 探针（edge_server.py） |
| `/v1/cgc/resume` | POST | Token 流（edge_server.py） |

## 硬件要求

| GPU | 模型 | 量化 | 预估速度 |
|---|---|---|---|
| RTX 4090 | Qwen3.6-35B | IQ3_XXS | 40-60 tok/s |
| RTX 3090 | Qwen3.6-35B | IQ3_XXS | 25-35 tok/s |
| RTX 3060 | Qwen3-14B | Q4_K_M | 30-50 tok/s |
| CPU only | Qwen3-4B | Q4_K_M | 5-10 tok/s |

## 文件说明

```
installer/
├── PowerAuto-Installer.bat  — 安装检查脚本
├── start-server.bat         — 一键启动服务
├── download-model.bat       — 模型下载器
├── edge_server.py           — CGC Edge Server（高级）
├── README.md                — 本文档
└── models/                  — 模型文件目录（.gguf）
```

## 故障排除

**Q: 连接失败？**
- 确认 llama-server 已启动
- 检查端口是否被占用：`netstat -ano | findstr :8080`
- 检查防火墙是否放行

**Q: 速度很慢？**
- 确认 GPU 已启用（-ngl 99）
- 检查模型是否太大超出显存
- 尝试更小的量化版本

**Q: 输出质量差？**
- 尝试 temperature=0.7
- 检查 chat template 是否匹配
- 使用 edge_server.py 的 OpenAI 兼容层
