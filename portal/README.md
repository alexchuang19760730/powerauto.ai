# PowerAuto 端云侧部署管理 Portal

「模型市场 → 端侧／云侧部署」的**部署管理面**，以及 super user 登录后看到的**端侧 AI 目标与跨机资产能力复盘**。

> **分工边界**（按 2026-09-18 的裁定）：登录、用户与角色、网站后台管理**由另一个 agent 负责**；
> 这里只做「端云侧部署管理」＋ 消费它的角色结果。**接入点只有一个字段**，见 §4。

---

## 1. 为什么是「一个页面 ＋ 一个端点清单」

需求是「**先在端侧跑通，再切 endpoint 跑通 cloudflare**」。所以核心不是新推理后端，而是
**可切换的 base_url**。切换这个动作需要一份清单 —— 散在前端、Worker、白皮书三处必然漂移，
而漂移是静默的。所以：

| 文件 | 角色 | 唯一真相？ |
|---|---|---|
| `endpoints.json` | 推論端点（base URL）清单 | ✔ 是 |
| `fleet_export.json` | 端侧目标 ＋ 机队资产能力 ＋ 七日 ＋ 动能 | ✘ **否**，它是 CGC repo 的**汇出** |
| `index.html` | 只渲染，不计算任何指标 | — |
| `serve.py` | 端侧开发服务器（把探测搬到服务器端，避开 CORS） | — |

★ `fleet_export.json` 的数字**只在 CGC repo 算得出来**（动能、七日回填、目标绑定都在那里）。
网站端**不重算**：

```bash
# 在 CGC repo（flashkv-devserver）
python3 agent_harness/portal/build_fleet_portal.py --export   # 写 docs/fleet_export.json
# 然后把 docs/fleet_export.json 复制到本目录
```

两份实作必然漂移 ⇒ 页面上的每个数字都是转述，权威来源就是上面那条指令。

---

## 2. 先跑通端侧

```bash
cd portal
python3 serve.py --port 8090        # 只需标准函式库
# 打开 http://127.0.0.1:8090/
```

`serve.py` 提供：

| 路径 | 用途 |
|---|---|
| `GET /` | 入口页（super user 视图） |
| `GET /api/health?url=<endpoint>/v1/models` | **服务器端**探测（避开端侧／云侧不保证回 CORS 标头的问题） |
| `GET /api/endpoints` | 端点清单 |
| `GET /api/export` | 机队汇出 |

同一份 `index.html` 在**静态托管**下也能开：它先试 `/api/*`，没有就退回直接 `fetch` ＋ 读同目录的
`.json`。差别只在**探测能不能成功**（静态模式受 CORS 限制），不在资料怎么显示。

### 本轮的实测结果（2026-09-18）

| 端点 | 状态 | 原因 |
|---|---|---|
| `http://localhost:8080/v1` （端侧） | **unknown** | `Connection refused` —— edge_server 没在跑（不是坏掉） |
| `http://192.168.101.90:8080/v1` （跨机 Mac） | **unknown** | `Connection refused` —— 不在同区网或未启动 |
| `https://api.powerauto.ai/v1` （云侧·自订网域） | **unknown** | DNS 未解析 —— 这个网域还没设 |
| `https://powerauto-inference.powerauto-ai.workers.dev/v1` | **unknown** | `timed out` —— 见 §3 发现一 |

**四个都是 unknown（灰），不是红。** 连不上只说明「现在不知道」。

★ **可达 ≠ 是我們的服務**（2026-09-18 实测更正）：当时 port 8080 上是 **CGC fork 的 llama-server**
（`/v1/cgc/profile` 回 404），而只验可达性会让这一页对**别人的**服务报 **LIVE** —— 症状**完全像「一切正常」**。
所以 edge 端点带**身分断言**（`/v1/edge/status` 的 `object` 与 `endpoint_id`），新增两个状态：

| 状态 | 意义 | 颜色 |
|---|---|---|
| `live` | 可达，且（有宣告身分时）身分相符 | 绿 |
| `foreign` | 可达，但那个埠上的东西**不是我们的** | 红 |
| `unverified` | 可达，但身分**验不了**（探测途中网路错）—— 不假装 LIVE | 琥珀 |
| `unknown` | 连不上／非 200 | 灰 |
| `blocked` | 主機不在白名单 | 琥珀 |

---

## 3. 两个网络层的发现（会改变架构，必须先讲）

### ★ 发现一：`*.workers.dev` 从中国大陆不可达 —— 云侧必须挂自订网域

实测量测（同一个沙箱，对照组正常）：

```
example.com                    HTTP 200        ← 对照
www.cloudflare.com             HTTP 200        ← 对照
powerauto.ai                   HTTP 200        ← 对照
powerauto-inference.powerauto-ai.workers.dev   超时

DNS: powerauto-inference.powerauto-ai.workers.dev → 118.184.26.113
                                                  ↑ 这是中国 IP，不是 Cloudflare 的 104.x／172.x
```

⇒ 这是 **DNS 污染**，不是 Worker 挂了。所以：

- `endpoints.json` 的 `cloud-custom-domain`（`https://api.powerauto.ai/v1`）才是**可用形式**；
- `cloud-workers-dev` 那一笔**保留是为了可追溯**（白皮书 §4.2 记的就是它），但**不该是默认值**；
- 要做的事（在 Cloudflare 侧，不属于本目录）：把 `api.powerauto.ai` 指到 Worker `powerauto-inference`，
  并把 Worker 的 CORS 标头设为允许 `https://powerauto.ai`。

### ★ 发现二：`powerauto.ai` 解析到 GitHub Pages ⇒ PHP 后台不会执行

```
powerauto.ai → 185.199.108.153   ← GitHub Pages 的 IP
```

而 repo 里有 `admin/index.php`（PHP session ＋ `password_hash`）与 `.htaccess`（自述「GoDaddy / Apache 优化」）。

⇒ **两套并存**：GitHub Pages 是静态的，`/admin/` 在那里**只会被当纯文本下载**，不会执行。
所以：

- **闸门不能靠 PHP**（除非确定网站是走 GoDaddy 那一套）；
- 若确定走 GitHub Pages，**服务器端闸门只能用 Cloudflare**（Worker 验签，或 Cloudflare Access）。

这一条要先确认你是哪一种部署，否则「super user 才能看到」会做在一个跑不起来的宿主上。

---

## 4. 角色：接入点只有一个字段

页面上的角色来自（优先级由高到低）：

```js
?role=superuser            // 查询参数，方便端侧先跑通
window.POWERAUTO_ROLE      // 另一个 agent 登录后注入
（都没有）→ "superuser"     // 端侧开发默认
```

**★ 前端判断角色不构成访问控制** —— 任何人都能抓到这份 HTML。
真正的闸门必须在服务器端。所以接入方式二选一：

| 做法 | 说明 |
|---|---|
| **Cloudflare Worker 验签后回传** | 登录态（JWT／签名 cookie）在边缘验，只有通过才把 portal 的 HTML 送出去 |
| **另一个 agent 的服务器端模板** | 由它的 PHP／后端在渲染时决定要不要输出这一页 |

不论哪一种，**我方只需要它给一个 `role` 值**。`role ∈ {superuser, admin, user}`（按 2026-09-18 的裁定）。

---

## 5. 安全：我查了什么（方法可复现）

密钥不该出现在公开 repo。我**只查形状、不印值**，结论是**目前干净**：

| 检查 | 结果 |
|---|---|
| 公开 repo 的 HEAD（`CROSS_PLATFORM_DEPLOYMENT_GUIDE.md`、`playground/index.html`…） | 命中的全是**占位字串**：`ghp_你的…`、`hf_你的t…`、`cfut_你…`（含中文）；`Bearer` 是说明文字；`hf_token` 是**栏位名** |
| **历史**（该文件第 1 版，commit message 自己写着 "redacted"） | 只有 `hf_...`（三个点，文件里的省略号）⇒ **历史里也没有真 token** |
| `config.php`（公开档） | 纯内容设定（PHP 数组），**无凭据** |

⇒ **不需要轮换。**

一句建议（不展开）：把密钥放**私有 repo 的 `secrets.json`** 能解决「两端都要用」，
但它是「分发」而不是「保管」—— 任何被 clone 的机器、任何有 read 权限的人都能拿到，而且没有轮换审计。
更稳的是 Cloudflare Secrets Store／`gh secret set`／1Password CLI，让密钥**永远不落到工作区的档案里**。

---

## 6. 本目录**没有**做的事（明确列出来）

- **登录与用户管理**（另一个 agent）：本目录只消费 `role`。
- **模型市场的「部署」按钮**（`models/index.html` 里每个模型已有 `cloud: true`，但还没有 `edge` 栏位与部署动作）：
  这是下一步，形态见 §7。
- **`installer/edge_server.py` 的改动**：端侧服务已经能跑（`:8080` OpenAI 相容、`:8081` worker、`/v1/cgc/profile`）。
- **Cloudflare 侧的任何改动**（自订网域、CORS、Worker 的验签）。
- **端侧上报**：CGC 机队入口已有一份「端点状态契约」（`agent_harness/portal/endpoints/`），
  端侧跑起来后回报那一份，机队表就会自动出现这一端。

---

## 7. 下一步（建议顺序，与「先端侧再云侧」一致）

1. **端侧跑通**：`serve.py` ＋ 起 `edge_server.py` ⇒ 第一个端点变 **LIVE**（现在是 unknown）。
2. **模型市场加 `edge` 栏位**：每个模型标「能不能在端侧跑」（参数量／量化／需要的 RAM），
   以及一个「部署到我的端侧」按钮 —— 产生对应的 installer 指令。
3. **云侧挂自订网域**：`api.powerauto.ai` → Worker（见 §3 发现一），然后 `cloud-custom-domain` 变 LIVE。
4. **闸门落地**：按 §4 选一种，把 `role` 真正接起来。
5. **端侧回报**：跑起来的端侧把状态写进 CGC 的 `endpoints/<id>.json`（或直接 POST `/api/report`），
   机队表就会多一列 —— 「跨机资产能力复盘」才算真的闭环。

---

## 8. 自测

```bash
python3 serve.py --self-test      # 16 格
```

涵盖：静态档 200、`/api/export`、`/api/endpoints`、**白名单外 URL ⇒ blocked**、
**连不上 ⇒ unknown（不是 fail）**、**路径跳脱用原始 socket 送字面 `..` 被拒**、
**★ 身分不符 ⇒ foreign（含「假裝是別人服务」的 fixture）**、
**★ 身分相符 ⇒ live 且 `identity_ok=True`**、**★ 不宣告身分 ⇒ live 但明说「只驗了可達」**、
缺档 ⇒ 404 且是 JSON（不是 traceback）、看门狗（自测期间真目录不变）。

---

## 附錄：部署到 `powerauto.ai/portal/`（2026-09-18 追加）

本站台是 **GitHub Pages 靜態託管**（`powerauto.ai` → `185.199.108.153`），所以：

| 事項 | 實情 |
|---|---|
| 這一頁放哪 | repo 的 `portal/`，網址 `https://powerauto.ai/portal/` |
| 誰能開 | **任何人**。靜態頁面沒有伺服器端閘門，這一頁的角色只控制**顯示** |
| 能不能即時探測端點 | **不能**。頁面是 https、端點是 `http://localhost` ⇒ 瀏覽器以 mixed content 擋掉。<br>要探測得用端側 `python3 serve.py`，或讓雲端閘門代理探測 |
| PHP 後台（`/admin/`）能不能用 | 在 GitHub Pages 上**不會執行**（只會被當純文字下載）。若實際是 GoDaddy 那套宿主才有效 |

### 角色接入（只消費別人的登入結果）

我方**不做登入、不做使用者管理**（那是另一個 agent 的範圍）。接入點只有一個：

```js
window.POWERAUTO_ROLE = "superuser";   // 或 "admin" / "user"
```

或開發時用 `?role=superuser`。**預設是 `user`（最小權限）** —— 因為部署後這一頁任何人都能開，
預設給 superuser 等於「忘了接閘門就自動全開」。

| 角色 | 看得到的分區 |
|---|---|
| `superuser` | ①端点切换 ②端侧 AI 目标 ③机队资产能力 ④七日趋势 ⑤动能 |
| `admin` | ①②③ |
| `user` | ① |
| 未設定／無法辨識 | 視為 `user` |

★ **這一層是顯示，不是閘門。** 真正的閘門要在伺服器端；而 GitHub Pages 不跑 PHP
⇒ 若要做真閘門，只能走 Cloudflare（Worker 驗簽／Access）。詳見站台白皮書 §5。

### 資料從哪來

`fleet_export.json` 是 **CGC repo 產生的快照**，由
`python3 agent_harness/portal/build_fleet_portal.py --export` 產生。
本頁**只轉述、不重算**任何指標（動能、七日、目標綁定只有在 CGC repo 算得出來；
兩份實作必然漂移，而漂移是靜默的）。來源 commit 記在頁尾。

刷新方式：

```bash
cd <CGC repo> && python3 agent_harness/portal/build_fleet_portal.py --export
cp docs/fleet_export.json <本站 repo>/portal/fleet_export.json
```
