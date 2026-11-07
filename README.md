# vic3-mcp

读取本机 **Victoria 3** 存档（`.v3`）的 MCP 服务器。Agent 可以列出存档、解析国家数据，并给出建设 / 法案 / 外交建议。

默认测试存档：`~/Documents/Paradox Interactive/Victoria 3/save games/Qing_MCP.v3`（1836 大清）。

## 存档从哪来

| 路径 | 用途 |
|------|------|
| `~/Documents/Paradox Interactive/Victoria 3/save games/` | `.v3` 存档 |
| `~/Library/Application Support/Steam/steamapps/common/Victoria 3/game/` | 本地化与定义（国名、法案、建筑） |

游戏默认写入 **二进制 zip**。服务器用随附的 [rakaly](https://github.com/rakaly/cli) 把存档融化成文本后再抽数据。融化结果缓存在 `~/Library/Caches/vic3-mcp/`。

## 安装

```bash
uv sync
chmod +x scripts/run-mcp.sh vendor/rakaly
```

`vendor/rakaly` 是 macOS ARM64 的 rakaly 0.8.19。别的平台请从 https://github.com/rakaly/cli/releases 下载，放到 `vendor/rakaly` 或设置 `RAKALY`。

## 给 Grok 用

项目里已经有 `.grok/config.toml`。也可以：

```bash
grok mcp add vic3 -- /Users/i/myCode/vicroria/.venv/bin/python -m vic3_mcp
```

工作目录要能 import 到包：用上面的 venv，或 `scripts/run-mcp.sh`。

手动冒烟：

```bash
uv run python scripts/smoke.py Qing_MCP
```

## 网页（对话 + 指标 + 建议动作）

```bash
cp .env.example .env
# 编辑 .env：填 VIC3_LLM_BASE_URL、VIC3_LLM_API_KEY，模型默认 kimi-k3
uv sync
./scripts/run-web.sh
```

打开 http://127.0.0.1:8765

- 上：存档 KPI，支持自动刷新 / 手动刷新
- 左：和顾问对话（会读存档、改写右侧动作）
- 右：建议动作看板（启发式先填，对话后由模型更新）
- 模型设置：OpenAI 协议的 base URL、API Key、model（也可写在 `.env`）

## 工具

| 工具 | 作用 |
|------|------|
| `list_saves` | 列出本机存档 |
| `load_save` | 载入（默认 `Qing_MCP`） |
| `overview` | 日期、GDP、金库、列强 |
| `analyze_situation` | 风险 + 建议 |
| `country` / `economy` / `politics` / `pops` | 国家切片 |
| `diplomacy` / `military` / `technology` / `journal` | 外交/军事/科技/日志 |
| `buildings` / `states` / `rankings` | 建筑、省份、排行 |
| `compare_countries` | 多国对比 |
| `search_save` | 在融化文本里搜原始字段 |
| `localize` | 查游戏 loc |

`country` 参数：`player`、`CHI`、`GBR` 或数字 id。

## 环境变量

复制 `.env.example` 为 `.env` 后填写。`.env` 已在 `.gitignore` 中，不要提交。

| 变量 | 说明 |
|------|------|
| `VIC3_LLM_BASE_URL` | OpenAI 兼容接口，需含 `/v1` |
| `VIC3_LLM_API_KEY` | 接口密钥 |
| `VIC3_LLM_MODEL` | 模型名，默认 `kimi-k3` |
| `VIC3_SAVE_DIR` / `VIC3_USER_DIR` / `VIC3_GAME_DIR` | 覆盖存档/游戏路径 |
| `VIC3_MCP_CACHE` | 融化缓存目录 |
| `RAKALY` | rakaly 可执行文件路径 |
