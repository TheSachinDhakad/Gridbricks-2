# Grade report — public_03_load

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| arav_cancel_2 | 0.394 | +17.0% | 0.264 | +8.5% | 0.529 | +6.6% | 43% | 415 (409) |
| arav_kyc_1 | 0.487 | +35.8% | 0.270 | +25.4% | 0.622 | +3.6% | 23% | 418 (352) |
| arav_renewal_0 | 0.476 | +17.3% | 0.287 | +8.9% | 0.589 | +7.5% | 43% | 472 (408) |
| kest_cancel_2 | 0.400 | +18.9% | 0.265 | +9.2% | 0.538 | +7.8% | 52% | 419 (418) |
| kest_kyc_1 | 0.498 | +40.0% | 0.275 | +28.1% | 0.620 | +3.8% | 24% | 478 (370) |
| kest_renewal_0 | 0.471 | +17.2% | 0.284 | +7.2% | 0.590 | +8.3% | 45% | 435 (403) |
| nort_cancel_2 | 0.399 | +17.7% | 0.266 | +8.8% | 0.533 | +6.9% | 48% | 471 (368) |
| nort_kyc_1 | 0.428 | +20.2% | 0.246 | +14.5% | 0.607 | +1.9% | 11% | 424 (318) |
| nort_renewal_0 | 0.474 | +17.0% | 0.286 | +8.1% | 0.587 | +7.1% | 39% | 448 (419) |
| tide_cancel_2 | 0.398 | +16.1% | 0.267 | +9.2% | 0.529 | +5.5% | 46% | 412 (401) |
| tide_kyc_1 | 0.491 | +37.9% | 0.271 | +26.3% | 0.621 | +3.8% | 23% | 423 (376) |
| tide_renewal_0 | 0.475 | +17.3% | 0.285 | +8.1% | 0.589 | +7.9% | 45% | 487 (425) |
| ALL | 0.449 | +22.5% | 0.272 | +13.0% | 0.580 | +6.2% | 36% | 5302 (4667) |

## Changes applied by the controller

117 applied — neutral: 69, beneficial: 48

- nort_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.013 → **neutral**
- nort_cancel_2 v2 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.001 didΔ=+0.003 → **neutral**
- kest_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.013 → **neutral**
- kest_cancel_2 v2 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.001 didΔ=+0.003 → **neutral**
- arav_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.013 → **neutral**
- arav_cancel_2 v2 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.001 didΔ=+0.003 → **neutral**
- tide_renewal_0 v2 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=-0.013 → **neutral**
- tide_cancel_2 v2 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.001 didΔ=+0.003 → **neutral**
- nort_cancel_2 v3 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.003 → **neutral**
- kest_cancel_2 v3 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.003 → **neutral**
- arav_cancel_2 v3 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.003 → **neutral**
- tide_cancel_2 v3 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.003 → **neutral**
- nort_cancel_2 v4 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v4 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v4 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v4 (controller_auto) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.020 → **neutral**
- nort_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- arav_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- tide_renewal_0 v3 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.019 → **neutral**
- nort_renewal_0 v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.034 → **beneficial**
- arav_renewal_0 v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.034 → **beneficial**
- tide_renewal_0 v4 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.034 → **beneficial**
- kest_cancel_2 v5 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.024 → **beneficial**
- kest_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.010 → **neutral**
- nort_cancel_2 v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.025 → **beneficial**
- arav_cancel_2 v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- arav_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.025 → **beneficial**
- arav_renewal_0 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- tide_cancel_2 v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.026 → **beneficial**
- kest_renewal_0 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v7 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_renewal_0 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.037 → **beneficial**
- kest_cancel_2 v8 (controller_auto) dims=['welcome_message', 'voice'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- arav_cancel_2 v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- kest_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.137 → **beneficial**
- kest_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- tide_cancel_2 v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v10 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- kest_cancel_2 v11 (controller_auto) dims=['voice'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- nort_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.023 didΔ=+0.146 → **beneficial**
- kest_renewal_0 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.071 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.151 → **beneficial**
- arav_renewal_0 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.072 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v10 (controller_auto) dims=['welcome_message', 'voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- arav_cancel_2 v10 (controller_approved) dims=['cohorts', 'welcome_message', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v12 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- arav_cancel_2 v11 (controller_auto) dims=['welcome_message', 'voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v11 (controller_auto) dims=['welcome_message'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- kest_cancel_2 v13 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- arav_cancel_2 v12 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v12 (controller_auto) dims=['welcome_message'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_cancel_2 v10 (controller_approved) dims=['cohorts', 'welcome_message', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v14 (controller_auto) dims=['voice'] engageΔ=+0.005 didΔ=+0.000 → **neutral**
- arav_cancel_2 v13 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v13 (controller_auto) dims=['welcome_message'] engageΔ=+0.002 didΔ=+0.000 → **neutral**
- arav_cancel_2 v14 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.072 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v14 (controller_auto) dims=['voice'] engageΔ=+0.017 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.016 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v16 (controller_auto) dims=['voice'] engageΔ=+0.012 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.071 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v16 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v11 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v17 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- kest_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.011 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v18 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- arav_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.203 → **beneficial**
- nort_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v16 (controller_approved) dims=['cohorts', 'welcome_message', 'schedule'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- kest_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.216 → **beneficial**
- nort_cancel_2 v12 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v13 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- nort_cancel_2 v14 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- kest_cancel_2 v17 (controller_auto) dims=['welcome_message'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- kest_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.012 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- kest_cancel_2 v18 (controller_auto) dims=['welcome_message'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- kest_cancel_2 v19 (controller_auto) dims=['welcome_message'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- tide_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.016 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v16 (controller_auto) dims=['voice'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- kest_cancel_2 v20 (controller_auto) dims=['welcome_message'] engageΔ=+0.001 didΔ=+0.000 → **neutral**
- nort_cancel_2 v17 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_cancel_2 v18 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_cancel_2 v19 (controller_auto) dims=['voice'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- nort_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.162 → **beneficial**
- tide_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.237 → **beneficial**
- nort_cancel_2 v20 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v21 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v22 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v23 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- nort_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.160 → **beneficial**
- arav_kyc_1 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.095 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- tide_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.095 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v7 (controller_approved) dims=['voice'] engageΔ=+0.012 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v19 (controller_auto) dims=['voice'] engageΔ=+0.011 didΔ=+0.000 → **beneficial**
- kest_kyc_1 v4 (controller_approved) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.095 didΔ=+0.128 → **beneficial**
- nort_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.019 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- nort_kyc_1 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.096 didΔ=+0.044 → **beneficial**
- tide_kyc_1 v5 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.094 → **beneficial**
- nort_renewal_0 v9 (controller_approved) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- nort_kyc_1 v5 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.098 → **beneficial**

## Governance

```
{
  "approval_requests": 42,
  "decisions": {
    "approved": 38,
    "rejected": 4,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 4
  },
  "applied_via_approval": 38,
  "auto_applied": 79,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nort_kyc_1": 1,
    "nort_cancel_2": 2,
    "kest_renewal_0": 2,
    "arav_kyc_1": 1,
    "arav_cancel_2": 2,
    "tide_kyc_1": 1,
    "tide_cancel_2": 1,
    "nort_renewal_0": 2,
    "arav_renewal_0": 2,
    "tide_renewal_0": 2,
    "kest_kyc_1": 1,
    "kest_cancel_2": 1
  }
}
```

## Incidents

```
[]
```

## Decaying variants — share of in-population calls still on the variant, by day after onset

```
{
  "nort_renewal_0:welcome_message=W3": {
    "3": 0.649,
    "4": 0.649
  },
  "kest_renewal_0:welcome_message=W3": {
    "3": 0.651,
    "4": 0.652
  },
  "arav_renewal_0:welcome_message=W3": {
    "3": 0.65,
    "4": 0.651
  },
  "tide_renewal_0:welcome_message=W3": {
    "3": 0.644,
    "4": 0.651
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0