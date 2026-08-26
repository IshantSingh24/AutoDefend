# Razorpay Autonomous Defense Assembler
## Track 02: AI Risk Manager | Hackathon 2026

> Stop the merchant losing money to fraud, returns and chargebacks.

An agentic AI system that automatically assembles evidence and submits bank-compliant chargeback rebuttals — or honestly recommends acceptance when the evidence does not support filing.

---

## Architecture

```
Razorpay Dispute Webhook
        |
        v
FastAPI Ingestion Layer
        |
        v
  LangGraph FSM
  |            |           |
Classifier -> Parallel  -> Evaluator -> [Compiler -> Submit]
Agent        Executors     Agent        |
             (Logistics,               -> [Halt: Recommend Accept]
              Security,                -> [Halt: Human Review]
              CRM)
```

## Quick Start

```bash
# 1. Clone and enter directory
git clone <repo-url>
cd razorpay-chargeback-defender

# 2. Copy environment file
cp backend/.env.example backend/.env
# Edit backend/.env with your Razorpay test keys

# 3. Start full stack
docker-compose up --build

# 4. Webhook is live at:
# POST http://localhost:8000/webhook/dispute

# 5. Dashboard at:
# http://localhost:8000/dashboard
```

## Running the Demo (4 Scenarios)

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for step-by-step demo walkthrough.

```bash
# Scenario A: Strong evidence -> rebuttal filed automatically
curl -X POST http://localhost:8000/demo/PAY_FIGHT_WIN

# Scenario B: In-transit -> system recommends acceptance
curl -X POST http://localhost:8000/demo/PAY_HALT_TRANSIT

# Scenario C: API timeout -> routed to human review
curl -X POST http://localhost:8000/demo/PAY_API_TIMEOUT

# Scenario D: Weak evidence -> below confidence threshold, accept recommended
curl -X POST http://localhost:8000/demo/PAY_WEAK_EVIDENCE
```

## ML Metrics (Held-Out Test Set)

Evaluated on 20 labeled disputes not seen during development:

| Metric | Value |
|--------|-------|
| Precision | TBD after Step 12 |
| Recall | TBD after Step 12 |
| F1 Score | TBD after Step 12 |
| False Positive Count | TBD |
| False Positive Cost (avg) | TBD Rs. |

Run evaluation: `cd backend && pytest tests/test_metrics.py -v`

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI + Uvicorn |
| Orchestration | LangGraph (FSM) |
| LLM | Google Gemini 1.5 Pro |
| Database | PostgreSQL |
| Cache/Queue | Redis + Celery |
| PDF | ReportLab + Jinja2 |
| Metrics | scikit-learn |

## Track 02 Compliance

- **Defense-Only:** Full compliance checklist in [MASTER_STRATEGY_PLAN.md](Profile/MASTER_STRATEGY_PLAN.md#16-defense-only-compliance-checklist)
- **Honest Metrics:** Precision/recall with false-positive cost — see Section 15 of strategy plan
- **Held-Out Test Set:** 20 labeled disputes, ground truth set before any model development

## Project References

- [Problem Statement](About/Problem_solution.md)
- [Master Strategy Plan](Profile/MASTER_STRATEGY_PLAN.md)
- [Build Roadmap](Profile/BUILD_ROADMAP.md)
