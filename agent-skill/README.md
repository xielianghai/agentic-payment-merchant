# Agent Skill (HEG Flight)

第二种客户端形态：通过 OpenClaw / QClaw + mcporter 调用 Adapter MCP 工具，复用同一支付栈。

本项目只维护 **`heg-flight`** 技能；不再包含旧的通用结账技能。

## 目录

| 目录 | 用途 |
|------|------|
| `qclaw/heg-flight/` | **主源** — 改 skill 从这里改 |
| `openclaw/` | OpenClaw 本地开发版（由 sync 脚本生成） |
| `clawhub/heg-flight/` | ClawHub 发布包（由 sync 脚本生成） |
| `scripts/generate-mcporter.py` | 唯一 mcporter 结构定义（相对/绝对路径） |

## 维护 skill（一条命令）

改完 `qclaw/heg-flight/` 后：

```bash
cd agent-skill
chmod +x sync-heg-flight-skill.sh scripts/generate-mcporter.py
./sync-heg-flight-skill.sh
```

默认会：

1. 同步 `openclaw/`、`clawhub/heg-flight/`（scripts、SKILL.md、相对路径 `mcporter.json`）
2. 安装/刷新 QClaw：`~/.qclaw/skills/heg-flight/` + 绝对路径 `mcporter.json` + 更新 `~/.qclaw/openclaw.json`

可选：

```bash
./sync-heg-flight-skill.sh --no-qclaw    # 只同步仓库内 openclaw/clawhub
./sync-heg-flight-skill.sh --qclaw-only  # 只刷新 QClaw 安装
```

不会覆盖：`openclaw/README.md`、`clawhub/heg-flight/PUBLISH.md`、各目录 `references/setup.md`。

## 配置

```bash
export MERCHANT_HOME=/path/to/agentic-payment-merchant
export MCPORTER_CONFIG=$HOME/.qclaw/skills/heg-flight/mcporter.json
```

## 前置

1. 启动 HEG Flight、商户运营管理、Adapter、支付栈：
   ```bash
   ./scripts/start-all.sh
   ~/.qclaw/skills/heg-flight/scripts/start-backend.sh   # buyer MCP :8100-8103
   ```

2. 在 QClaw 中启用 `mcporter` 与 `heg-flight`（`sync-heg-flight-skill.sh` 会自动配置）

## OpenClaw 本地使用

```bash
export MERCHANT_HOME=/path/to/agentic-payment-merchant
export MCPORTER_CONFIG=$MERCHANT_HOME/agent-skill/openclaw/mcporter.json
MERCHANT_HOME=$MERCHANT_HOME $MERCHANT_HOME/agent-skill/openclaw/scripts/start-backend.sh
```

然后在 OpenClaw 配置中启用 `mcporter` 与 `heg-flight`。

## MCP 服务

`mcporter.json` 包含：

- `ap2-merchant-adapter` → `adapter/mcp/server.py`（UCP+AP2 航班目录/购物车/结账）
- `ap2-buyer` / `ap2-cp` / `ap2-mpp` → 本地 HTTP MCP（支付授权与结算）

商户工具：
- `search_inventory` / `check_product` / `assemble_cart`
- `create_checkout` / `complete_checkout`
