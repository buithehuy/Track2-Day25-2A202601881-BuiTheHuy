"""M5 — Optimization Report: combine M1-M4 into baseline-vs-optimized (deck §1/§11).

Run: python missions/m5_report.py   ->  outputs/report.md + outputs/savings.png
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
from missions._common import num, catalog_by_type, ROOT
from finops import report, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing

DAYS = 30
# one tier down for over-provisioned ("util-lie") GPUs
RIGHTSIZE_MAP = {"H100": "A100", "H200": "H100", "A100": "A10G", "A10G": "L4", "L4": "L4"}


def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)
    cat = catalog_by_type()

    # --- buckets ---
    infer_savings = (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]

    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = 0.0
    for lie in r1["lies"]:
        cur = lie["gpu_type"]
        tgt = RIGHTSIZE_MAP.get(cur, cur)
        delta = num(cat[cur]["on_demand_hr"]) - num(cat[tgt]["on_demand_hr"])
        rightsize_savings += max(0.0, delta) * 24 * DAYS

    levers = {
        "Inference (cascade/cache/batch)": round(infer_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "Right-size util-lies": round(rightsize_savings),
        "Kill idle GPUs": round(idle_savings),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    # --- sustainability snapshot ---
    median_tokens = 800
    wh = sustainability.wh_per_query(median_tokens)
    cleanest = min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get)
    cheapest = min(sustainability.REGION_PRICE_KWH, key=sustainability.REGION_PRICE_KWH.get)
    sust = {
        "wh_per_query": wh,
        "carbon_g": sustainability.carbon_g(wh, "us-east-1"),
        "best_region": cleanest, "best_region_carbon": sustainability.REGION_CARBON[cleanest],
        "cheapest_region": cheapest, "cheapest_region_price": sustainability.REGION_PRICE_KWH[cheapest],
        "reasoning_cost": r2["reasoning_cost"],
        "reasoning_pct_traffic": r2["reasoning_pct_traffic"],
        "reasoning_cost_pct": r2["reasoning_cost_pct"],
        "optimized_wh": r2["optimized_wh"], "capped_wh": r2["capped_wh"],
        "capped_cost": r2["capped_cost"],
    }

    md = report.build_report(baseline, optimized, levers, sustainability=sust,
                             baseline_per_m=r2["baseline_per_m"], optimized_per_m=r2["optimized_per_m"])
    right_lines = [
        "",
        "## Technical analysis and extensions",
        "",
        "### Why GPU-Util lies",
        "",
        "`gpu-h100-4` reports ~98% GPU-Util but only ~0.19 MFU. GPU-Util measures "
        "whether kernels/clock activity are present, not useful FLOPs completed. "
        "Memory stalls, small kernel launches, synchronization, or I/O can keep the "
        "device busy while producing little computation; the full GPU-hour is still billed.",
        "",
        "### Extension 1 — interruption- and duration-aware purchasing",
        "",
        "The policy uses per-GPU spot interruption rates (5–12%), keeps interruptible "
        "jobs on spot when checkpointable, and requires a 30-day minimum before a "
        "reserved recommendation. This avoids reserving short-lived capacity; the "
        f"dataset changes the purchasing result to {r3['savings_pct']:.1f}% monthly savings "
        "versus on-demand. Re-evaluate rates and 1yr/3yr terms with live provider data.",
        "",
        "### Extension 2 — MBU-aware right-sizing",
        "",
        "Candidates must meet observed bandwidth plus 10% headroom and then minimize "
        "HBM footprint before comparing $/GB-VRAM. This prevents choosing the cheapest "
        "hourly GPU that cannot sustain the workload's memory traffic. See M1 output "
        "for the per-GPU recommendation and hourly saving.",
        "",
        "### Extension 4 — reasoning budget",
        "",
        f"Reasoning is {r2['reasoning_pct_traffic']:.1f}% of requests but {r2['reasoning_cost_pct']:.1f}% "
        f"of optimized inference cost (${r2['reasoning_cost']:.2f}/day). It consumes "
        f"{r2['optimized_wh']:,.0f} Wh/day in the model. The observed traffic is already "
        f"below the 10% cap ({r2['capped_reasoning_requests']} requests would be capped), "
        "so the measured cap produces no further reduction; route new reasoning traffic "
        "only for high-complexity tasks and alert when its share exceeds 10%.",
        "",
        "### Action priority",
        "",
        "1. Apply cascade, cache, and batch policies first: they reduce the inference "
        f"unit cost from ${r2['baseline_per_m']:.3f} to ${r2['optimized_per_m']:.3f}/1M-token.\n"
        "2. Stop idle GPUs and remediate low-MFU util-lies.\n"
        "3. Use spot with checkpoints for interruptible jobs; reserve only stable capacity.\n"
        "4. Shift flexible workloads to the cleanest region after checking latency and data residency.",
    ]
    md += "\n".join(right_lines) + "\n"
    out_md = os.path.join(ROOT, "outputs", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w") as f:
        f.write(md)
    png = report.savings_waterfall(levers, os.path.join(ROOT, "outputs", "savings.png"))

    if verbose:
        print("== M5 Optimization Report ==")
        print(md)
        print(f"\nWritten: outputs/report.md" + (f" + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"))

    return {"baseline_monthly": round(baseline), "optimized_monthly": round(optimized),
            "levers": levers, "total_savings_pct": round(total_pct, 1)}


if __name__ == "__main__":
    run()
