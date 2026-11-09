# Grade report — dev_variant_a

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| ks_cancel | 0.383 | +10.6% | 0.263 | +7.1% | 0.500 | +2.2% | 0% | 68 (53) |
| nw_kyc | 0.402 | +61.2% | 0.255 | +53.7% | 0.606 | -0.5% | -9% | 31 (57) |
| nw_renewal | 0.474 | +12.7% | 0.287 | +11.1% | 0.555 | +0.9% | -2% | 53 (59) |
| ALL | 0.417 | +19.1% | 0.270 | +15.0% | 0.539 | +2.1% | -3% | 152 (169) |

## Changes applied by the controller

19 applied — neutral: 7, beneficial: 11, harmful: 1

- nw_renewal v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.015 → **neutral**
- ks_cancel v2 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=-0.006 didΔ=+0.003 → **neutral**
- ks_cancel v3 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=-0.006 didΔ=+0.003 → **neutral**
- ks_cancel v4 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=-0.000 didΔ=+0.000 → **neutral**
- nw_renewal v3 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.000 didΔ=+0.000 → **neutral**
- ks_cancel v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nw_kyc v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.108 → **beneficial**
- nw_renewal v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.021 → **beneficial**
- ks_cancel v6 (controller_auto) dims=['voice'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- nw_renewal v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.041 → **beneficial**
- ks_cancel v7 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.025 → **beneficial**
- ks_cancel v8 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- nw_kyc v4 (controller_approved) dims=['prompt_version'] engageΔ=-0.046 didΔ=+0.000 → **harmful**
- nw_renewal v6 (controller_approved) dims=['voice'] engageΔ=+0.025 didΔ=+0.000 → **beneficial**
- nw_kyc v5 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.615 → **beneficial**
- nw_renewal v7 (controller_approved) dims=['voice'] engageΔ=+0.027 didΔ=+0.000 → **beneficial**
- nw_renewal v8 (controller_approved) dims=['welcome_message'] engageΔ=+0.018 didΔ=+0.000 → **beneficial**
- nw_kyc v6 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.281 → **beneficial**
- nw_kyc v7 (controller_approved) dims=['voice'] engageΔ=+0.091 didΔ=+0.000 → **beneficial**

## Governance

```
{
  "approval_requests": 12,
  "decisions": {
    "approved": 10,
    "rejected": 2,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 2
  },
  "applied_via_approval": 10,
  "auto_applied": 9,
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
    "workflow": "nw_kyc",
    "at": "D2 12:00",
    "mttr_minutes": 165,
    "fixed_by": "controller_approved"
  },
  {
    "type": "supervisor_edit",
    "workflow": "ks_cancel",
    "at": "D3 16:00"
  },
  {
    "type": "did_flagged",
    "workflow": "nw_kyc",
    "at": "D4 11:00",
    "flagged_did_share_by_day": {
      "4": 0.756,
      "5": 0.591,
      "6": 0.464,
      "7": 0.208,
      "8": 0.106
    }
  }
]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nw_renewal:voice=V4": {
    "3": 0.277,
    "4": 0.428,
    "5": 0.0,
    "6": 0.0,
    "7": 0.0,
    "8": 0.0
  }
}
```

Credits used: 8 · validation runs: 2 · LLM fix calls: 0