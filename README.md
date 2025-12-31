# access-anomaly-detector

Explainable, likelihood-based anomaly detection for **who is accessing sensitive resources, when, and how**.

This project builds **empirical behavioral baselines** from access logs and scores new access events using **probabilistic anomaly metrics** (negative log-likelihood), producing both a numeric risk score and a human-readable explanation.

> **v0.1** focuses on transparency, statistical grounding, and ease of deployment  
> (file-based logs + SQLite + Python stdlib HTTP).

---

## 1. Problem statement

Organizations handling sensitive assets (e.g. prototype devices, confidential builds, internal R&D tools) typically have:

- authentication and authorization
- audit logs of access events

What is often missing is **behavior-aware monitoring**, such as:

- *Is this access statistically unusual for this actor?*
- *Is this resource normally touched by many people or only a few?*
- *Does this pattern resemble credential misuse or data exfiltration?*

`access-anomaly-detector` sits **on top of existing logs** and answers:

> **“How anomalous is this access event, quantitatively, and why?”**

---

## 2. Modeling approach

### 2.1 Empirical baselines

The system maintains **online empirical distributions** using SQLite.  
These baselines summarize historical access behavior and are updated incrementally after each event (no batch training required).

| Baseline | Interpretation |
|--------|----------------|
| Actor × hour histogram | Empirical distribution of access hours per actor (P(hour \| actor)) |
| Actor × resource type counts | Empirical distribution of resource types per actor (P(resource_type \| actor)) |
| Actor × device fingerprints | Whether a device has been seen before for an actor |
| Resource × recent actors | Number of distinct actors who accessed a resource recently |

These empirical summaries form the statistical foundation for likelihood-based anomaly scoring in later stages.


### 2.2 Likelihood-based anomaly signals

Instead of heuristic thresholds, v0.1 uses **smoothed probability estimates** and converts them into anomaly magnitudes.

#### (a) Unusual access time
For an actor `a` and UTC hour `h`:

P(h | a) = (c[a,h] + α) / ( Σ_h c[a,h] + 24 · α )

Anomaly magnitude:

S_hour = -log( P(h | a) ) / -log( P_min )

where `P_min` corresponds to an unseen hour under Laplace smoothing.

#### (b) Unusual resource type
Similarly:

P(r | a) = (c[a,r] + α) / ( Σ_r c[a,r] + K · α )

where `K`` is an approximate vocabulary size (configurable) and `c[a,r]` is the count of accesses by actor `a` to resource type `r`.

#### (c) Discrete risk signals
Some signals are naturally categorical and remain binary:

- **New device** for the actor
- **Rare resource** (few distinct actors in recent history)
- **High sensitivity asset**

Each signal produces:
- a numeric contribution \([0,1]\)
- a human-readable explanation

---

### 2.3 Composite risk score

Signals are combined via a **weighted additive risk model**:

\[
\text{score} = \min\left(1,\; \sum_i w_i \cdot S_i \right)
\]

Weights are configurable in `config.yaml`.

The final score is mapped to:
- `LOW`
- `MEDIUM`
- `HIGH`

using configurable thresholds.

---

## 3. Explainability

Every scored event includes:

- **Numeric score** (0–1)
- **Risk bucket**
- **Triggered signals**, e.g.:
  - “Unusual hour for actor (UTC hour=3, P=0.0042)”
  - “Unusual resource_type for actor (HW_LAB_DEVICE)”
  - “New device_fingerprint for this actor”
- **Recommended actions**, aligned with severity

No black-box models or opaque embeddings are used in v0.1.

---

## 4. Architecture

```text
+---------------------+
| Access Logs (JSONL) |
+----------+----------+
           |
           v
+---------------------+
| Feature Extraction  |
| - Likelihood scores |
| - Discrete signals  |
+----------+----------+
           |
           v
+---------------------+
| Scoring Engine      |
| - Weighted sum      |
| - Thresholding     |
+----------+----------+
           |
           v
+---------------------+
| Output / API        |
| - JSONL batch       |
| - HTTP /score       |
+---------------------+
```
Baselines persisted in SQLite (incremental, online).

## 5. Usage

### 5.1 Installation

```
bash
python -m venv .venv
source .venv/bin/activate
pip install -e
```

### 5.2 Endpoints
- `GET /health`
- `POST /score`

### 5.3 Example request
```
curl -X POST http://127.0.0.1:8080/score \
  -H 'Content-Type: application/json' \
  -d '{
    "timestamp":"2025-12-21T03:21:00Z",
    "actor_id":"alice",
    "resource_id":"proto-999",
    "resource_type":"HW_LAB_DEVICE",
    "action":"READ_LOGS",
    "project_id":"proj-x",
    "device_fingerprint":"dfp-NEW",
    "sensitivity":"PROTOTYPE_CRITICAL"
  }'
```


