# Grade report — dev_variant_b_null

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.377 | +9.4% | 0.265 | +9.6% | 0.496 | -0.9% | 0% | 61 (48) |
| nw_kyc | 0.462 | +28.1% | 0.292 | +21.8% | 0.607 | +2.7% | 0% | 21 (20) |
| nw_renewal | 0.461 | +7.0% | 0.294 | +11.1% | 0.537 | -3.4% | -330% | 53 (94) |
| ALL | 0.423 | +12.3% | 0.280 | +12.4% | 0.533 | -0.8% | -38% | 135 (162) |

## Changes applied by the controller

14 applied — neutral: 9, beneficial: 4, harmful: 1

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.013 → **neutral**
- ks_cancel v2 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.003 → **neutral**
- ks_cancel v3 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.003 → **neutral**
- ks_cancel v4 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- ks_cancel v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.000 didΔ=+0.119 → **beneficial**
- ks_cancel v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.023 → **beneficial**
- ks_cancel v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.010 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.035 → **beneficial**
- nw_renewal v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.018 → **neutral**
- nw_kyc v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.143 → **beneficial**
- nw_renewal v7 (controller_approved) dims=['prompt_version'] engageΔ=-0.047 didΔ=+0.000 → **harmful**
- nw_renewal v8 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**

## Governance

```
{
  "approval_requests": 7,
  "decisions": {
    "approved": 6,
    "rejected": 1,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 1
  },
  "applied_via_approval": 6,
  "auto_applied": 8,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nw_renewal": 1,
    "nw_kyc": 1,
    "ks_cancel": 1
  }
}
```

## Incidents

```
[
  {
    "type": "supervisor_edit",
    "workflow": "nw_renewal",
    "at": "D4 10:30",
    "mttr_minutes": 210,
    "fixed_by": "controller_approved"
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{}
```

Credits used: 8 · validation runs: 2 · LLM fix calls: 0