# Agentic Payment Merchant Demo

端到端智能体支付商户 Demo：**A2A（传输）+ UCP（商务交易）+ AP2（授权支付）** 三层协议栈。

## 子工程

| 目录 | 说明 | 端口 |
|------|------|------|
| `merchant-management/` | 商户运营管理平台（入驻、能力登记、注册表） | 9100 / 5273 |
| `adapter/` | Adapter（UCP 商户门面 + 动态路由 + MCP 工具） | 8200 |
| `payment-stack/` | AP2 支付栈（Shopping Agent、CP、MPP、TS、监控） | 8090–8105 |
| `web-chat-client/` | Web 对话客户端 | 5183 |
| `agent-skill/` | OpenClaw / QClaw / ClawHub `heg-flight` 智能体技能 | — |

外部依赖：**HEG Flight**（`/Users/ouyang/AI-coding/payment/heg_flight_mock`，端口 9000）

## 快速启动

```bash
# 1. 复制环境变量并填写 DEEPSEEK_API_KEY
cp .env.example .env

# 2. 启动 HEG Flight（外部仓库）
cd ../heg_flight_mock && ./scripts/start-backend.sh

# 3. 一键启动 Demo（本仓库）
./scripts/start-all.sh
```

## 端到端流程

1. 打开商户运营管理 http://127.0.0.1:5273 → 入驻 HEG Flight
2. 打开 Web 对话客户端 http://127.0.0.1:5183
3. 对话购票（HP 或 HNP）→ Adapter 经 UCP 翻译到 HEG → AP2 完成支付

详细文档见 [docs/RUNBOOK.md](docs/RUNBOOK.md)。
