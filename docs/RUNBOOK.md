# Agentic Payment Merchant Demo — 运行手册

## 前置条件

- MySQL 8.x（127.0.0.1:3306，密码 12345678）
- Python 3.10+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv)（AP2 支付栈依赖）
- HEG Flight 外部仓库已 clone

## 环境配置

```bash
cp .env.example .env
# 编辑 .env，填写 DEEPSEEK_API_KEY
```

## 启动顺序

### 1. HEG Flight（外部）

```bash
cd ../heg_flight_mock
./scripts/start-backend.sh
```

### 2. 本仓库 Demo

```bash
./scripts/start-all.sh
```

或分步启动：

```bash
# 商户运营管理
./merchant-management/scripts/start-backend.sh   # :9100
./merchant-management/scripts/start-frontend.sh  # :5273

# Adapter（UCP 门面）
./scripts/start-adapter.sh                       # :8200

# 支付栈 + Web 对话客户端
cd payment-stack && ./start.sh
```

## 端到端流程

1. **入驻**：打开 http://127.0.0.1:5273 →「商户入驻」→ 一键入驻 HEG Flight
2. **验证注册表**：`curl http://127.0.0.1:9100/api/v1/registry/merchants`
3. **UCP 发现**：`curl http://127.0.0.1:8200/.well-known/ucp`
4. **购票对话**：打开 http://127.0.0.1:5183
   - HP + Card：`Buy Singapore Airlines SIN to PVG economy June 10 for 1 adult now with card.`
   - HNP + Card：`Book SIN to PVG economy June 10 for 1 adult, budget USD 600.`
5. **核验订单**：HEG 管理台 http://127.0.0.1:5173 或 HEG REST API

## 协议栈

| 层 | 协议 | 组件 |
|----|------|------|
| 传输 | A2A | Web Chat ↔ Shopping Agent (:8090) |
| 商务 | UCP | Adapter UCP REST (:8200) → HEG .do REST |
| 支付 | AP2 | Mandate / Checkout JWT / MPP (:8093) |

## 端口一览

| 服务 | 端口 |
|------|------|
| HEG Flight | 9000 / 5173 |
| 商户运营管理 | 9100 / 5273 |
| Adapter | 8200 |
| Shopping Agent | 8090 |
| CP / MPP / x402 | 8092 / 8093 / 8094 |
| Trusted Surface | 8104 |
| Monitor Scheduler | 8105 |
| Web Chat Client | 5183 |

## openClaw 技能

```bash
# 见 agent-skill/openclaw/README.md
export AP2_HOME=$PWD/payment-stack
export MCPORTER_CONFIG=$PWD/agent-skill/openclaw/mcporter.json
```

## 停止

```bash
./scripts/stop-all.sh
```

## UCP+AP2 桥接验证

```bash
# 需 HEG (:9000) 与 Adapter (:8200) 已启动
./scripts/test-ucp-ap2-bridge.sh
```

验证 UCP checkout session 上 `ap2_mandate` 附加与 finalize 状态同步。
