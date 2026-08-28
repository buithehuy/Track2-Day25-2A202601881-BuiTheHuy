"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def rightsize_by_mbu(summary: list[dict], catalog: dict, max_mbu: float = 0.35) -> list[dict]:
    """Suggest a cheaper GPU that can sustain the observed memory bandwidth.

    Candidates must have enough HBM for the current class and at least the
    observed bandwidth (with a 10% headroom).  This prevents choosing solely
    by hourly price and makes the recommendation useful for decode workloads.
    """
    recommendations = []
    for row in summary:
        current = catalog[row["gpu_type"]]
        if row["mbu"] >= max_mbu:
            continue
        required_bw = num(current["peak_bw_tbs"]) * row["mbu"] * 1.10
        current_hbm = num(current["hbm_gb"])
        candidates = []
        for gpu_type, candidate in catalog.items():
            if (num(candidate["hbm_gb"]) >= current_hbm
                    and num(candidate["peak_bw_tbs"]) >= required_bw):
                cost_per_gb = num(candidate["on_demand_hr"]) / num(candidate["hbm_gb"])
                candidates.append((cost_per_gb, gpu_type, candidate))
        if not candidates:
            continue
        # Prefer the smallest HBM footprint that fits, then the best $/GB.
        # Otherwise a large MI300X would win on $/GB while being wastefully
        # over-provisioned for an 80GB workload.
        _, target_type, target = min(candidates, key=lambda x: (num(x[2]["hbm_gb"]), x[0], x[1]))
        current_rate = num(current["on_demand_hr"])
        target_rate = num(target["on_demand_hr"])
        recommendations.append({
            "gpu_id": row["gpu_id"], "current_gpu": row["gpu_type"],
            "recommended_gpu": target_type, "mbu": row["mbu"],
            "required_bw_tbs": round(required_bw, 3),
            "current_cost_per_gb": round(current_rate / current_hbm, 4),
            "recommended_cost_per_gb": round(num(target["on_demand_hr"]) / num(target["hbm_gb"]), 4),
            "hourly_savings": round(max(0.0, current_rate - target_rate), 2),
        })
    return recommendations


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    rightsizing = rightsize_by_mbu(summary, cat)
    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        print("\nMBU-aware right-sizing ($/GB-VRAM + bandwidth):")
        for r in rightsizing:
            print(f"  {r['gpu_id']}: {r['current_gpu']} -> {r['recommended_gpu']} "
                  f"(${r['current_cost_per_gb']:.4f} -> ${r['recommended_cost_per_gb']:.4f}/GB, "
                  f"${r['hourly_savings']:.2f}/GPU-h saved)")

    return {"summary": summary, "lies": lies, "idle_waste_daily": round(idle_waste, 2),
            "rightsizing": rightsizing}


if __name__ == "__main__":
    run()
