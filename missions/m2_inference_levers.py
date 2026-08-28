"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing
from finops import sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = 0.0
    total_tokens = 0
    reasoning_cost = non_reasoning_cost = 0.0
    optimized_wh = capped_wh = 0.0
    capped_cost = 0.0
    reasoning_requests = 0
    capped_reasoning_requests = 0
    # Cap reasoning traffic at 10% by removing the synthetic 6x reasoning
    # output tax from the least expensive reasoning requests first.
    reasoning_rows = [r for r in rows if bool(int(num(r["is_reasoning"]))) ]
    cap_count = int(len(rows) * 0.10)
    keep_reasoning_ids = {id(r) for r in sorted(
        reasoning_rows, key=lambda x: int(num(x["output_tokens"]))
    )[:cap_count]}
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        opt_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        is_reasoning = bool(int(num(r["is_reasoning"])))
        row_cost = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        if is_reasoning:
            reasoning_requests += 1
            reasoning_cost += row_cost
        else:
            non_reasoning_cost += row_cost
        wh = sustainability.wh_per_query(inp + out, is_reasoning=is_reasoning)
        optimized_wh += wh
        capped = is_reasoning and id(r) not in keep_reasoning_ids
        if capped:
            capped_reasoning_requests += 1
            # Approximate the policy action: route the capped request without
            # the reasoning expansion, while retaining its normal discounts.
            normal_out = max(1, round(out / 6))
            capped_wh += sustainability.wh_per_query(inp + normal_out, is_reasoning=False)
            capped_cost += pricing.request_cost(inp, normal_out, pin, pout,
                                                cached_in=cached, batch=is_batch)
        else:
            capped_wh += wh
            capped_cost += row_cost

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print(f"reasoning : {reasoning_requests}/{len(rows)} requests, ${reasoning_cost:,.2f} "
              f"({reasoning_cost / opt_cost * 100:.1f}% of optimized cost)")
        print(f"10% reasoning cap: ${opt_cost:,.2f} -> ${capped_cost:,.2f}; "
              f"energy {optimized_wh:,.1f} -> {capped_wh:,.1f} Wh")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "reasoning_requests": reasoning_requests,
        "reasoning_pct_traffic": round(reasoning_requests / len(rows) * 100, 1),
        "reasoning_cost": round(reasoning_cost, 4),
        "reasoning_cost_pct": round(reasoning_cost / opt_cost * 100, 1) if opt_cost else 0.0,
        "optimized_wh": round(optimized_wh, 2), "capped_wh": round(capped_wh, 2),
        "capped_cost": round(capped_cost, 4),
        "capped_reasoning_requests": capped_reasoning_requests,
    }


if __name__ == "__main__":
    run()
