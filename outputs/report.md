# NimbusAI — GPU Cost Optimization Report

**Period:** monthly  
**Baseline spend:** $27,133  
**Optimized spend:** $14,626  
**Projected savings:** $12,507  (**46%**)

**Baseline unit cost:** $6.488/1M-token  
**Optimized unit cost:** $1.126/1M-token  

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,212 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cleanest region: europe-north1 (30 gCO2/kWh)
- Cheapest electricity: us-east-wa ($0.055/kWh)
- Reasoning traffic: 8.4% of requests; $1.40 (16.5% of optimized inference cost)
- Reasoning energy policy (cap at 10%): 31,675 Wh -> 31,675 Wh

_Figures are June-2026 as-of snapshots; re-baseline before acting._
## Technical analysis and extensions

### Why GPU-Util lies

`gpu-h100-4` reports ~98% GPU-Util but only ~0.19 MFU. GPU-Util measures whether kernels/clock activity are present, not useful FLOPs completed. Memory stalls, small kernel launches, synchronization, or I/O can keep the device busy while producing little computation; the full GPU-hour is still billed.

### Extension 1 — interruption- and duration-aware purchasing

The policy uses per-GPU spot interruption rates (5–12%), keeps interruptible jobs on spot when checkpointable, and requires a 30-day minimum before a reserved recommendation. This avoids reserving short-lived capacity; the dataset changes the purchasing result to 39.1% monthly savings versus on-demand. Re-evaluate rates and 1yr/3yr terms with live provider data.

### Extension 2 — MBU-aware right-sizing

Candidates must meet observed bandwidth plus 10% headroom and then minimize HBM footprint before comparing $/GB-VRAM. This prevents choosing the cheapest hourly GPU that cannot sustain the workload's memory traffic. See M1 output for the per-GPU recommendation and hourly saving.

### Extension 4 — reasoning budget

Reasoning is 8.4% of requests but 16.5% of optimized inference cost ($1.40/day). It consumes 31,675 Wh/day in the model. The observed traffic is already below the 10% cap (0 requests would be capped), so the measured cap produces no further reduction; route new reasoning traffic only for high-complexity tasks and alert when its share exceeds 10%.

### Action priority

1. Apply cascade, cache, and batch policies first: they reduce the inference unit cost from $6.488 to $1.126/1M-token.
2. Stop idle GPUs and remediate low-MFU util-lies.
3. Use spot with checkpoints for interruptible jobs; reserve only stable capacity.
4. Shift flexible workloads to the cleanest region after checking latency and data residency.
