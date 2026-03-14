# Pain Point Scoring Framework

The `analyze.py` script uses a weighted composite scoring algorithm to rank pain points from 0-100.

---

## Composite Score Formula

```
composite_score = (
    frequency_weight     × frequency_norm     +
    cross_source_weight  × cross_source_norm  +
    intensity_weight     × intensity_norm     +
    recency_weight       × recency_score      +
    commercial_weight    × commercial_norm
) × 100
```

### Weight Assignments

| Factor | Weight | Rationale |
|--------|--------|-----------|
| `cross_source_count` | **0.30** | Biggest signal — same complaint in multiple independent sources = validated real pain |
| `frequency` | **0.25** | How often the complaint appears across all posts/reviews combined |
| `commercial_intent` | **0.15** | Complaints from paying customers (app reviews, G2) are worth more than free product complaints |
| `intensity` | **0.20** | Average upvotes/reactions/thumbs — proxy for "many people agree" |
| `recency` | **0.10** | Recent complaints > old ones (problems may already be solved) |

---

## Factor Normalization

Each factor is normalized to a 0.0–1.0 range before weighting:

### Frequency (raw → normalized)
```
frequency_norm = min(frequency / 50, 1.0)
```
- 50+ mentions → 1.0 (maximum)
- 25 mentions → 0.5
- 10 mentions → 0.2

### Cross-Source Count (raw → normalized)
```
cross_source_norm = min(cross_source_count / 8, 1.0)
```
- 8+ different sources → 1.0 (maximum)
- 4 sources → 0.5
- 1 source → 0.125

### Intensity (avg upvotes/reactions → normalized)
```
intensity_norm = min(avg_intensity / 200, 1.0)
```
- 200+ avg upvotes → 1.0
- 100 upvotes → 0.5
- 10 upvotes → 0.05

### Recency Score
```
if any mention in current year:   recency_score = 1.0
if any mention in previous year:  recency_score = 0.8
otherwise:                        recency_score = 0.5
```

### Commercial Intent Score
```
if source includes app reviews, G2, Trustpilot, Amazon:  commercial_norm = 1.0
otherwise (Reddit, HN, SO — free users):                  commercial_norm = 0.4
```

---

## Score Interpretation

| Score Range | Meaning | Action |
|-------------|---------|--------|
| **80-100** | Extremely high-signal pain point. Multiple sources, paying customers complaining, recent, frequent. | Build this immediately. |
| **60-79** | Strong pain point. Validated across 3+ sources. | Worth serious investigation. |
| **40-59** | Moderate signal. Present but not overwhelming. | Dig deeper before committing. |
| **20-39** | Weak signal. Isolated complaints or old posts. | Low priority; may be a niche-within-a-niche. |
| **0-19** | Noise. Single source, low engagement, or very old. | Ignore unless you have other data. |

---

## Cross-Source Validation Multiplier Effect

The `cross_source_count` factor (weight 0.30) is the most important. Here's why:

A complaint appearing in only one place (e.g., one Reddit post) could be:
- One person's unique frustration
- An edge case
- Already fixed in a new product version

The same complaint appearing on Reddit **AND** G2 **AND** Stack Overflow means:
- Multiple independent people discovered the same problem
- The problem persists across different contexts
- It likely affects a wide range of users

**Example:**

Pain point: "No way to export data to CSV"

| Scenario | Cross-Source Score | Final Score Impact |
|----------|-------------------|-------------------|
| Found only on Reddit | 1/8 = 0.125 | +3.75 pts |
| Found on Reddit + G2 | 2/8 = 0.25 | +7.5 pts |
| Found on Reddit + G2 + SO + App Store | 4/8 = 0.5 | +15 pts |
| Found across 8 sources | 8/8 = 1.0 | +30 pts |

---

## Clustering Algorithm

Pain points are clustered using **Jaccard similarity on token sets**:

1. Tokenize each complaint: extract words >3 chars, remove stopwords
2. For each unassigned complaint, find all others with Jaccard similarity ≥ 0.25
3. Group them into a cluster with the first complaint as the representative

**Threshold tuning:**
- `--cluster-threshold 0.25` (default): Moderate grouping, captures similar phrasings
- `--cluster-threshold 0.15`: More aggressive grouping, fewer but broader clusters
- `--cluster-threshold 0.40`: Conservative grouping, more specific clusters

---

## Examples: High vs. Low Scoring Pain Points

### High-Scoring Example (Score: 84)

**Pain point:** "Can't export data to multiple formats"

| Factor | Raw Value | Normalized | Weighted |
|--------|-----------|------------|---------|
| frequency | 38 | 0.76 | 0.19 |
| cross_source_count | 6 | 0.75 | 0.225 |
| intensity | 156 avg upvotes | 0.78 | 0.156 |
| recency | current year mention | 1.0 | 0.10 |
| commercial | from G2 + App Store | 1.0 | 0.15 |
| **Total** | | | **0.821 → 82.1** |

Why it's high: Multiple paying customers (commercial_intent=1.0) complaining consistently across 6 different platforms, with recent high-engagement posts.

---

### Low-Scoring Example (Score: 18)

**Pain point:** "UI feels outdated"

| Factor | Raw Value | Normalized | Weighted |
|--------|-----------|------------|---------|
| frequency | 4 | 0.08 | 0.02 |
| cross_source_count | 1 | 0.125 | 0.0375 |
| intensity | 3 avg upvotes | 0.015 | 0.003 |
| recency | 3 years ago | 0.5 | 0.05 |
| commercial | Reddit only | 0.4 | 0.06 |
| **Total** | | | **0.1705 → 17.05** |

Why it's low: Single source (just Reddit), few mentions, low engagement, old post, not commercial context. "UI feels outdated" is also vague — not clearly solvable.

---

## Opportunity Gap Detection

Separate from scoring, `analyze.py` identifies **opportunity gaps** — mentions that explicitly describe a missing feature or workaround:

**Trigger phrases:**
```
"i wish", "why can't", "there's no way to", "no way to",
"need a way to", "should be able to", "is there a",
"does anyone know how to", "missing feature", "please add"
```

These represent **stated demand** — users articulating exactly what they want. A pain point with a high composite score **and** matching opportunity phrases is the ideal target.

---

## Niche-Level Verdict

The overall niche verdict is based on the average composite score of the top N pain points:

```
avg_score ≥ 60 AND max_cross_source ≥ 3 → "high" demand, "Worth building"
avg_score ≥ 40 OR max_cross_source ≥ 2  → "moderate" demand, "Dig deeper"
otherwise                                 → "low" demand, "Consider another angle"
```
