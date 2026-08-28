"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(baseline_usd: float, optimized_usd: float, levers: dict,
                 sustainability: dict | None = None, period: str = "monthly",
                 baseline_per_m: float | None = None, optimized_per_m: float | None = None) -> str:
    """Return a markdown cost-optimization report."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}  ",
        f"**Baseline spend:** ${baseline_usd:,.0f}  ",
        f"**Optimized spend:** ${optimized_usd:,.0f}  ",
        f"**Projected savings:** ${savings:,.0f}  (**{pct:.0f}%**)",
        "",
    ]
    if baseline_per_m is not None and optimized_per_m is not None:
        lines += [f"**Baseline unit cost:** ${baseline_per_m:.3f}/1M-token  ",
                  f"**Optimized unit cost:** ${optimized_per_m:.3f}/1M-token  ", ""]
    lines += [
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")
    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Cleanest region: {sustainability.get('best_region', 'n/a')} "
            f"({sustainability.get('best_region_carbon', 0):.0f} gCO2/kWh)",
            f"- Cheapest electricity: {sustainability.get('cheapest_region', 'n/a')} "
            f"(${sustainability.get('cheapest_region_price', 0):.3f}/kWh)",
        ]
        if "reasoning_cost" in sustainability:
            lines += [f"- Reasoning traffic: {sustainability.get('reasoning_pct_traffic', 0):.1f}% of requests; "
                      f"${sustainability.get('reasoning_cost', 0):.2f} ({sustainability.get('reasoning_cost_pct', 0):.1f}% of optimized inference cost)",
                      f"- Reasoning energy policy (cap at 10%): {sustainability.get('optimized_wh', 0):,.0f} Wh -> "
                      f"{sustainability.get('capped_wh', 0):,.0f} Wh"]
    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str) -> str:
    """Write a simple savings bar chart PNG. Returns the path. No-op if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    names = list(levers.keys())
    vals = [levers[n] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, vals, color="#2e548a")
    ax.set_ylabel("Savings (USD / month)")
    ax.set_title("GPU cost savings by FinOps lever")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
