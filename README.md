# Customer 360 + Win-back Engine | Salesforce Data Cloud

> **Status: In Progress** — Data ingestion, DLO-to-DMO mapping, and identity resolution are complete. Calculated Insights and customer segmentation are the next phases.

Building a customer intelligence solution that unifies CRM, e-commerce, and engagement data into consolidated customer profiles for a Customer 360 use case — with a win-back segment targeting lapsed, high-value customers.

---

## Architecture Overview

```
CRM (Contacts)          E-Commerce (Customers / Orders / Products)      Web Events
      │                              │                                       │
      ▼                              ▼                                       ▼
 Data Stream                    Data Stream                            Data Stream
(Contact_Home DLO)          (Order / Customer DLOs)               (Web Event DLO)
      │                              │                                       │
      └──────────────────────────────┼───────────────────────────────────────┘
                                     ▼
                           DLO → DMO Mapping
                     (Individual, Sales Order, Product)
                                     │
                                     ▼
                         Identity Resolution (Data 360)
                      Email · Phone · Fuzzy Name + City rules
                                     │
                                     ▼
                          Unified Individual Profiles
                                     │
                    ┌────────────────┴──────────────────┐
                    ▼                                   ▼
           Calculated Insights                   Segmentation
        (LTV · Recency · Churn risk)       (Win-back: lapsed + high-LTV)
                    │                                   │
                    └────────────────┬──────────────────┘
                                     ▼
                             Activation / Action
                         (Marketing Cloud · Flow · etc.)
```

---

## What's Built (Phase 1 & 2)

### Data Ingestion
- Three source systems loaded via Data Cloud Data Streams:
  - **CRM** — Salesforce Contacts (`Contact_Home` DLO)
  - **E-Commerce** — Customers, Orders, Order Items, Products
  - **Web** — Clickstream / engagement events
- Synthetic dataset: **500 CRM contacts + 600 e-commerce customers** across India, with intentional overlap for identity resolution testing.

### DLO → DMO Mapping
- Source DLOs mapped to canonical Data Model Objects:
  - `Individual` (unified person)
  - `Sales Order` + `Sales Order Product`
  - `Unified Individual` (post-resolution)

### Identity Resolution
- Match ruleset applied in Data Cloud Data 360:
  - Rule 1: Exact normalized email
  - Rule 2: Exact normalized phone
  - Rule 3: Fuzzy first name + exact last name + matching city/state
- Results exported and scored against a ground-truth person map (see `scripts/ir_simulate_and_score.py`).

---

## What's Planned (Phase 3 & 4)

| Phase | Feature | Description |
|---|---|---|
| 3 | Calculated Insights | LTV score, recency bucket, churn-risk flag per Unified Individual |
| 3 | Engagement Score | Weighted rollup of web events + order history |
| 4 | Win-back Segment | Filter: lapsed > 90 days AND LTV > threshold AND churn risk = high |
| 4 | Activation | Publish segment to Marketing Cloud / trigger Flow for outreach |

---

## Synthetic Dataset

Located in `data/synthetic/`. Generated to mirror realistic Indian e-commerce and CRM data patterns, with a controlled ground truth for identity resolution evaluation.

| File | Records | Description |
|---|---|---|
| `crm_contacts.csv` | 500 | CRM contacts with name, email, phone, address |
| `ecom_customers.csv` | 600 | E-commerce customer profiles |
| `ecom_orders.csv` | ~1 200 | Orders with status, amount, channel |
| `ecom_order_items.csv` | ~3 000 | Line items per order |
| `products.csv` | 50 | Product catalog |
| `web_events.csv` | ~5 000 | Clickstream events |
| `ground_truth_person_map.csv` | — | Answer key: source record → true person ID |

---

## Identity Resolution Simulator

`scripts/ir_simulate_and_score.py` lets you benchmark match rulesets against the ground truth **before and after** deploying them in Data Cloud.

```bash
# Simulate multiple rulesets against synthetic data
python3 scripts/ir_simulate_and_score.py simulate

# Score your real Data Cloud identity resolution output
python3 scripts/ir_simulate_and_score.py score \
  UnifiedLinks__dlm.csv \
  Contact_Home__dll.csv
```

Outputs pairwise precision, recall, F1, false-merge count, and missed-merge count — broken down by match signal strength (email+phone / email only / phone only / fuzzy only).

---

## Data Cloud Metadata (force-app)

Metadata retrieved from the connected org lives in `force-app/main/default/`:

| Metadata Type | What's here |
|---|---|
| `dataStreamDefinitions/` | Data Stream configs for each source system |
| `dataModelObjects/` | DMO field mappings |
| `identityResolutionProcDefs/` | Match + reconciliation ruleset |
| `calculatedInsightDefinitions/` | *(planned — Phase 3)* |

---

## Reproduce in a Dev Org

```bash
# 1. Authenticate
sf org login web --set-default-dev-hub

# 2. Push metadata
sf project deploy start --source-dir force-app --target-org <alias>

# 3. Upload synthetic data via Data Cloud ingestion API or Data Streams UI
#    (see data/synthetic/)
```

---

## Tech Stack

- Salesforce Data Cloud (Data 360 / Customer Data Platform)
- Data Streams · DLO-to-DMO mapping · Identity Resolution
- Calculated Insights · Segmentation *(planned)*
- Python 3 — identity resolution simulation & scoring
- SFDX · Salesforce CLI v2
