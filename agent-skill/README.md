# Agent Skill (HEG Flight)

第二种客户端形态：通过 OpenClaw / QClaw + mcporter 调用 Adapter MCP 工具，复用同一支付栈。

本项目只维护 **`heg-flight`** 技能；不再包含旧的通用结账技能。

## 目录

| 目录 | 用途 |
|------|------|
| `qclaw/heg-flight/` | QClaw 安装源 |
| `openclaw/` | OpenClaw 本地开发版 `heg-flight` skill |
| `clawhub/heg-flight/` | ClawHub 发布包 |

## QClaw 安装（推荐）

```bash
cd agent-skill
chmod +x install-qclaw-skill.sh
./install-qclaw-skill.sh
```

安装目标：`~/.qclaw/skills/heg-flight/`。

脚本会复制技能文件、生成带绝对路径的 `mcporter.json`，并在 `~/.qclaw/openclaw.json` 中启用 `heg-flight` 与 `mcporter`。

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

2. 在 QClaw 中启用 `mcporter` 与 `heg-flight`（`install-qclaw-skill.sh` 会自动配置）

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
