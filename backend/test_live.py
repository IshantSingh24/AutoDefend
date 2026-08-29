"""
Quick live test — verifies agents work with real OpenAI API.
Run from backend/ dir: .venv\Scripts\python test_live.py
"""
import asyncio, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.agents.classifier import classifier_agent, REASON_CODE_KB
from app.graph.state import DisputeState
from app.config import get_settings

settings = get_settings()

def make_state(reason_code: str) -> DisputeState:
    return DisputeState(
        dispute_id=f"disp_live_test",
        payment_id="pay_live_001",
        merchant_id="merchant_test",
        reason_code=reason_code,
        amount=85000,
        phase="CHARGEBACK",
        raw_webhook={},
        evidence_collected={},
        audit_events=[],
        error_log=[],
    )

async def main():
    print(f"\n{'='*60}")
    print("AutoDefend -- Live Agent Test")
    print(f"OpenAI key set: {'YES' if settings.openai_api_key else 'NO'}")
    print(f"{'='*60}\n")

    # -- Test 1: Known KB code (no API call) --
    print("TEST 1: Known code VISA_10_4 (KB lookup - no LLM)")
    state = await classifier_agent(make_state("VISA_10_4"))
    print(f"  dispute_class:     {state['dispute_class']}")
    print(f"  evidence_strategy: {state['evidence_strategy']}")
    print(f"  confidence:        {state['initial_confidence']}")
    print(f"  audit source:      {state['audit_events'][0]['source']}")
    print("  PASS\n")

    # -- Test 2: Known KB code MC_4853 --
    print("TEST 2: Known code MC_4853 (KB lookup - no LLM)")
    state = await classifier_agent(make_state("MC_4853"))
    print(f"  dispute_class:     {state['dispute_class']}")
    print(f"  executors:         {state['evidence_strategy']}")
    print("  PASS\n")

    # -- Test 3: Unknown code -> REAL OpenAI API call --
    print("TEST 3: Unknown code 'AMEX_F24' -> LLM fallback (REAL API CALL)")
    state = await classifier_agent(make_state("AMEX_F24"))
    print(f"  dispute_class:     {state['dispute_class']}")
    print(f"  evidence_strategy: {state['evidence_strategy']}")
    print(f"  confidence:        {state['initial_confidence']}")
    print(f"  audit source:      {state['audit_events'][0]['source']}")
    print("  PASS\n")

    print(f"{'='*60}")
    print("All tests done.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(main())
