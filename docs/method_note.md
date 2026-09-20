# APIx Airfare Index Methodology Note (`docs/method_note.md`)

**Target Audience**: Official Statisticians, Price Index Methodology Reviewers, Econometricians.

---

## 1. Executive Summary & Index Philosophy

APIx is a real-time, high-frequency airfare price index tracking domestic air travel inflation across India. To eliminate product-mix bias (quality change from shifting flight schedules, cabin classes, or carrier market shares), APIx strictly implements a **matched-model (like-with-like) elementary cell structure** aggregated via **geometric Jevons price relatives** and weighted by official **DGCA passenger traffic volume**.

---

## 2. Directed Sectors & Route Basket Selection

APIx models domestic air travel as **directed origin-destination sectors** (e.g., `DEL-BOM`, `DEL-BLR`, `BOM-BLR`, `DEL-CCU`, `BLR-HYD`, `MAA-DEL`).

### Rationale for Directed Sectors:
1. **Asymmetric Pricing & Demand Dynamics**: Morning outbound flights from major metro hubs (e.g. Delhi to Mumbai for business) experience dramatically higher demand and steeper price curves than reverse flows at the same hour.
2. **Passenger Flow Asymmetry**: Business travel is predominantly outbound on Monday morning and inbound on Friday evening; modeling undirected pairs would mask directional inflation trends.
3. **Regulatory Alignment**: DGCA passenger traffic metrics track directional city-pair passenger volumes.

---

## 3. Elementary Cell Definition & Jevons Index Formula

### 3.1 Cell Definition
An **elementary cell** $c$ holds fixed:
$$\text{Cell } c = \text{Route } r \times \text{Lead Window } T \times \text{Carrier } k \times \text{Fare Type } f \times \text{Stops } s \times \text{Time Band } b$$

### 3.2 Jevons Price Relative Formula
Within cell $c$ on date $t$, individual flight quote price relatives $r_{i,t} = p_{i,t} / p_{i,0}$ are aggregated using the **Jevons unweighted geometric mean**:
$$I_{c,t} = \exp\left( \frac{1}{N_{c,t}} \sum_{i \in c, t} \ln\left(\frac{p_{i,t}}{p_{i,0}}\right) \right)$$

Where:
- $p_{i,t}$ is the observed total fare (or base fare) for flight $i$ on search date $t$.
- $p_{i,0}$ is the reference base price for flight $i$ in the base period ($t=0$, default `2026-09-20`).
- $N_{c,t}$ is the number of valid, non-outlier quotes in cell $c$ on date $t$.

---

## 4. Missing Cell Handling & Weight Re-Normalization

### 4.1 Carry-Forward Policy
If an elementary cell $c$ is missing on date $t$, its last observed index level $I_{c,t-1}$ is carried forward for at most **2 consecutive days**.

### 4.2 Dynamic Weight Re-Normalization
Beyond 2 days, the cell $c$ is temporarily excluded for period $t$. Cell weights $v_c$ within route $r$ are dynamically re-normalized across active cells:
$$v_{c,t}' = \frac{v_c}{\sum_{k \in \text{active}(r,t)} v_k}$$
Ensuring that $\sum_{c \in \text{active}(r,t)} v_{c,t}' = 1.0$.

---

## 5. Route Index & National APIx Level Aggregation

### 5.1 Route Index ($I_{r,t}$)
$$I_{r,t} = \sum_{c \in \text{active}(r,t)} v_{c,t}' \cdot I_{c,t}$$

### 5.2 National APIx Level ($\text{APIx}_t$)
$$\text{APIx}_t = 100 \cdot \sum_{r} w_r \cdot I_{r,t}$$

Where route weights $w_r$ are derived from official DGCA monthly passenger traffic figures:
$$w_r = \frac{\text{DGCA Passengers}_r}{\sum_{k} \text{DGCA Passengers}_k}$$

---

## 6. Sensitivity Analysis & Lead-Time Weighting

Index stability is evaluated across 3 alternative lead-time weight mixtures:
1. **Equal Weights**: $T+1 (0.20), T+7 (0.20), T+15 (0.20), T+30 (0.20), T+45 (0.20)$
2. **Front-Loaded**: $T+1 (0.40), T+7 (0.30), T+15 (0.15), T+30 (0.10), T+45 (0.05)$
3. **Long-Horizon**: $T+1 (0.05), T+7 (0.10), T+15 (0.15), T+30 (0.30), T+45 (0.40)$

Sensitivity testing demonstrates maximum index variation $\le 3.5$ index points under extreme weighting shifts.
