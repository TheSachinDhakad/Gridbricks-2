# Grade report — public_03_load

## Outcomes vs baseline (no-op controller)

| workflow | conclusion rate | Δ | pickup | Δ | engagement | Δ | engagement gap captured | hallucinated calls (base) |
|---|---|---|---|---|---|---|---|---|
| arav_cancel_2 | 0.399 | +18.3% | 0.264 | +8.5% | 0.535 | +7.8% | 47% | 439 (409) |
| arav_kyc_1 | 0.442 | +23.3% | 0.254 | +17.8% | 0.607 | +1.1% | 14% | 434 (352) |
| arav_renewal_0 | 0.472 | +16.3% | 0.286 | +8.5% | 0.585 | +6.7% | 39% | 461 (408) |
| kest_cancel_2 | 0.394 | +17.2% | 0.266 | +9.8% | 0.527 | +5.6% | 40% | 407 (418) |
| kest_kyc_1 | 0.467 | +31.2% | 0.261 | +21.7% | 0.616 | +3.1% | 19% | 421 (370) |
| kest_renewal_0 | 0.474 | +17.9% | 0.286 | +8.2% | 0.585 | +7.4% | 39% | 471 (403) |
| nort_cancel_2 | 0.402 | +18.6% | 0.266 | +8.9% | 0.535 | +7.4% | 49% | 419 (368) |
| nort_kyc_1 | 0.482 | +35.6% | 0.272 | +26.4% | 0.608 | +2.1% | 14% | 431 (318) |
| nort_renewal_0 | 0.470 | +15.9% | 0.288 | +8.9% | 0.577 | +5.4% | 32% | 464 (419) |
| tide_cancel_2 | 0.403 | +17.3% | 0.266 | +8.7% | 0.539 | +7.6% | 55% | 404 (401) |
| tide_kyc_1 | 0.469 | +31.6% | 0.261 | +21.5% | 0.620 | +3.6% | 23% | 434 (376) |
| tide_renewal_0 | 0.471 | +16.5% | 0.286 | +8.3% | 0.583 | +6.8% | 36% | 452 (425) |
| ALL | 0.445 | +21.5% | 0.271 | +12.6% | 0.576 | +5.6% | 33% | 5237 (4667) |

## Changes applied by the controller

105 applied — neutral: 58, beneficial: 46, harmful: 1

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
- arav_cancel_2 v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.024 → **beneficial**
- arav_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=-0.000 didΔ=+0.024 → **beneficial**
- nort_cancel_2 v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- arav_cancel_2 v7 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.011 → **neutral**
- tide_cancel_2 v5 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v7 (controller_approved) dims=['cohorts', 'schedule'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v6 (controller_auto) dims=['voice', 'caller_id'] engageΔ=+0.000 didΔ=+0.025 → **beneficial**
- tide_cancel_2 v7 (controller_auto) dims=['welcome_message', 'caller_id'] engageΔ=+0.006 didΔ=+0.004 → **neutral**
- tide_cancel_2 v8 (controller_auto) dims=['welcome_message', 'caller_id'] engageΔ=+0.006 didΔ=+0.004 → **neutral**
- tide_cancel_2 v9 (controller_auto) dims=['welcome_message'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- kest_cancel_2 v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- arav_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.134 → **beneficial**
- kest_renewal_0 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- kest_renewal_0 v5 (controller_auto) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.039 → **beneficial**
- tide_renewal_0 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v8 (controller_auto) dims=['welcome_message'] engageΔ=+0.015 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.017 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v10 (controller_auto) dims=['welcome_message'] engageΔ=+0.019 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v10 (controller_auto) dims=['voice'] engageΔ=+0.016 didΔ=+0.000 → **beneficial**
- nort_renewal_0 v5 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.031 didΔ=+0.000 → **beneficial**
- nort_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.143 → **beneficial**
- tide_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.023 didΔ=+0.143 → **beneficial**
- nort_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- kest_cancel_2 v9 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v11 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_cancel_2 v12 (controller_auto) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v6 (controller_approved) dims=['welcome_message'] engageΔ=+0.072 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v10 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v11 (controller_auto) dims=['voice'] engageΔ=+0.012 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v11 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **neutral**
- kest_cancel_2 v12 (controller_auto) dims=['voice'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- kest_kyc_1 v2 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.022 didΔ=+0.154 → **beneficial**
- kest_cancel_2 v13 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- tide_cancel_2 v13 (controller_auto) dims=['voice'] engageΔ=+0.017 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v14 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- tide_cancel_2 v14 (controller_auto) dims=['voice'] engageΔ=+0.017 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.005 didΔ=+0.000 → **neutral**
- tide_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.016 didΔ=+0.000 → **beneficial**
- tide_cancel_2 v16 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_renewal_0 v6 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v10 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v11 (controller_auto) dims=['voice'] engageΔ=+0.010 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v12 (controller_auto) dims=['voice'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- nort_cancel_2 v13 (controller_auto) dims=['voice'] engageΔ=+0.007 didΔ=+0.000 → **neutral**
- tide_renewal_0 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.071 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v14 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v15 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_cancel_2 v16 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_renewal_0 v7 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.059 didΔ=+0.000 → **beneficial**
- nort_cancel_2 v17 (controller_auto) dims=['voice'] engageΔ=+0.006 didΔ=+0.000 → **neutral**
- nort_cancel_2 v18 (controller_auto) dims=['voice'] engageΔ=+0.003 didΔ=+0.000 → **neutral**
- kest_renewal_0 v6 (controller_approved) dims=['welcome_message', 'voice'] engageΔ=+0.071 didΔ=+0.000 → **beneficial**
- arav_renewal_0 v7 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=-0.012 didΔ=+0.000 → **harmful**
- nort_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.243 → **beneficial**
- nort_cancel_2 v19 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v20 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v21 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- nort_cancel_2 v22 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v12 (controller_auto) dims=['voice'] engageΔ=+0.011 didΔ=+0.000 → **beneficial**
- kest_kyc_1 v3 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.177 → **beneficial**
- kest_renewal_0 v7 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.005 didΔ=+0.000 → **neutral**
- tide_kyc_1 v3 (controller_approved) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.096 didΔ=+0.216 → **beneficial**
- kest_kyc_1 v4 (controller_approved) dims=['welcome_message'] engageΔ=+0.050 didΔ=+0.000 → **beneficial**
- kest_cancel_2 v16 (controller_auto) dims=['voice'] engageΔ=+0.011 didΔ=+0.000 → **beneficial**
- arav_cancel_2 v13 (controller_approved) dims=['cohorts', 'welcome_message', 'schedule'] engageΔ=+0.019 didΔ=+0.000 → **beneficial**
- arav_kyc_1 v3 (controller_approved) dims=['welcome_message', 'voice', 'caller_id'] engageΔ=+0.095 didΔ=+0.316 → **beneficial**
- nort_kyc_1 v4 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'caller_id', 'schedule'] engageΔ=+0.096 didΔ=+0.094 → **beneficial**
- kest_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.004 didΔ=+0.000 → **neutral**
- kest_kyc_1 v5 (controller_approved) dims=['voice', 'caller_id'] engageΔ=+0.044 didΔ=+0.112 → **beneficial**
- tide_kyc_1 v4 (controller_approved) dims=['caller_id'] engageΔ=+0.000 didΔ=+0.114 → **beneficial**
- arav_cancel_2 v14 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v15 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v16 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_cancel_2 v17 (controller_auto) dims=['welcome_message'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- arav_renewal_0 v8 (controller_approved) dims=['voice'] engageΔ=+0.000 didΔ=+0.000 → **neutral**
- tide_renewal_0 v7 (controller_approved) dims=['cohorts', 'welcome_message', 'voice', 'schedule'] engageΔ=+0.020 didΔ=+0.000 → **beneficial**

## Governance

```
{
  "approval_requests": 38,
  "decisions": {
    "approved": 33,
    "rejected": 5,
    "expired": 0
  },
  "rejection_reasons": {
    "approver declined (judgement call)": 5
  },
  "applied_via_approval": 32,
  "auto_applied": 73,
  "auto_apply_rejected": 0,
  "apply_conflicts": 0,
  "lapsed": 0,
  "peak_requests_per_24h": {
    "nort_kyc_1": 1,
    "nort_cancel_2": 1,
    "kest_renewal_0": 2,
    "arav_kyc_1": 1,
    "arav_cancel_2": 1,
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
    "3": 0.404,
    "4": 0.398
  },
  "kest_renewal_0:welcome_message=W3": {
    "3": 0.402,
    "4": 0.402
  },
  "arav_renewal_0:welcome_message=W3": {
    "3": 0.398,
    "4": 0.399
  },
  "tide_renewal_0:welcome_message=W3": {
    "3": 0.648,
    "4": 0.598
  }
}
```

Credits used: 0 · validation runs: 0 · LLM fix calls: 0