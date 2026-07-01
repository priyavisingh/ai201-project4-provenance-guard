# Provenance Guard — Planning Document

## Architecture

```
                    SUBMISSION FLOW
                    ===============

  Client                Flask API              Detection Pipeline           Output
  ------                ---------              ------------------           ------

  POST /submit  ----->  validate JSON
  {text,                generate content_id
   creator_id}           |
                        v
                   +----+----+
                   | Signal 1 |  Groq LLM assessment
                   | (semantic)|  --> llm_score (0-1)
                   +----+----+
                        |
                        v
                   +----+----+
                   | Signal 2 |  Stylometric heuristics
                   | (struct.) |  --> stylometric_score (0-1)
                   +----+----+
                        |
                        v
                   +----+----+
                   | Scoring  |  Weighted combine + disagreement dampening
                   | Engine   |  --> confidence (0-1), attribution
                   +----+----+
                        |
                        v
                   +----+----+
                   | Label    |  Map score to transparency label text
                   | Generator|
                   +----+----+
                        |
                        v
                   +----+----+
                   | Audit    |  SQLite structured log entry
                   | Log      |
                   +----+----+
                        |
                        v
                   JSON response {content_id, attribution, confidence,
                                  label, signal_scores, status}


                    APPEAL FLOW
                    ===========

  POST /appeal  ----->  lookup content_id in storage
  {content_id,          update status -> "under_review"
   creator_reasoning}  append appeal entry to audit log
                        |
                        v
                   JSON response {content_id, status, message}
```

A submission enters through `POST /submit` with `text` and `creator_id`. The API assigns a UUID `content_id`, runs both detection signals in sequence, combines their scores into a single confidence value and attribution label, generates the appropriate transparency label text, persists the decision to SQLite, and returns a structured JSON response. An appeal arrives via `POST /appeal` with a `content_id` and `creator_reasoning`; the system updates the content record's status to `under_review` and writes a linked appeal entry to the audit log so reviewers can see the original classification alongside the creator's reasoning.

### API Surface

| Endpoint | Method | Body | Returns |
|----------|--------|------|---------|
| `/submit` | POST | `{text, creator_id}` | `{content_id, attribution, confidence, label, signal_scores, status}` |
| `/appeal` | POST | `{content_id, creator_reasoning}` | `{content_id, status, message}` |
| `/log` | GET | — | `{entries: [...]}` |
| `/health` | GET | — | `{status: "ok"}` |

---

## Detection Signals

### Signal 1: LLM Semantic Assessment (Groq — llama-3.3-70b-versatile)

**What it measures:** Holistic semantic and stylistic coherence — whether the text reads like polished, template-driven AI prose or like authentic human expression with idiosyncrasies.

**Why it differs between human and AI:** LLM-generated text tends toward balanced sentence structures, hedging phrases ("it is important to note," "furthermore"), and topic sentences that feel mechanically complete. Human writing — especially casual or emotionally driven text — contains irregular rhythm, colloquialisms, and uneven emphasis.

**Output format:** A float `llm_score` from 0.0 to 1.0, where higher values indicate greater likelihood of AI generation.

**What it misses:** Heavily edited AI output, formal human academic writing, and non-native English speakers who write in a structured style may be misclassified. The LLM signal can also be influenced by its own biases about what "AI writing" looks like.

### Signal 2: Stylometric Heuristics (Pure Python)

**What it measures:** Structural statistical properties of the text:
1. **Sentence length variance** — humans vary sentence length more; AI tends toward uniform lengths.
2. **Type-token ratio (TTR)** — ratio of unique words to total words; AI text often repeats vocabulary.
3. **Punctuation density variance** — humans punctuate irregularly; AI tends toward consistent patterns.

**Why it differs between human and AI:** AI models optimize for readability and consistency, producing statistically smoother text. Human writers — especially in creative or informal contexts — produce noisier distributions.

**Output format:** A float `stylometric_score` from 0.0 to 1.0, where higher values indicate greater likelihood of AI generation (more uniformity = higher score).

**What it misses:** Deliberately stylized poetry with repetition, very short texts (insufficient data for statistics), and human writers who produce highly polished, uniform prose (e.g., technical documentation).

### Combining Signals

```
base_confidence = (0.55 * llm_score) + (0.45 * stylometric_score)

# Disagreement dampening: only when signals conflict in direction
# (one says AI >= 0.55, other says human <= 0.45) — pull toward 0.5
if signals_conflict and abs(llm_score - stylometric_score) > 0.3:
    base_confidence = base_confidence * 0.7 + 0.5 * 0.3

# Conservative bias: if LLM says AI but stylometrics say human, cap confidence
if llm_score > 0.7 and stylometric_score < 0.4:
    base_confidence = min(base_confidence, 0.65)

# Agreement boost when both signals lean AI
if llm_score >= 0.55 and stylometric_score >= 0.55:
    base_confidence = min(1.0, base_confidence + 0.04)
```

---

## Uncertainty Representation

**What does 0.6 mean?** A confidence of 0.6 means "moderately likely AI-generated, but not conclusive." The system leans toward AI attribution but the transparency label will read as **Uncertain** because we require higher confidence before making a definitive claim — especially given that false positives harm creators.

### Thresholds

| Range | Attribution | Label Category |
|-------|-------------|----------------|
| ≥ 0.70 | `likely_ai` | High-confidence AI |
| 0.40 – 0.69 | `uncertain` | Uncertain |
| < 0.40 | `likely_human` | High-confidence human |

The uncertain band is intentionally wide (31 percentage points) to avoid forcing binary judgments on borderline content.

### Validation Approach

Test with four deliberately chosen inputs:
1. Clearly AI-generated formal prose → expect score ≥ 0.70
2. Clearly casual human writing → expect score < 0.40
3. Formal human academic writing → expect mid-range (0.40–0.69)
4. Lightly edited AI output → expect mid-range (0.40–0.69)

Scores that cluster around 0.5 for borderline cases and separate clearly for extreme cases indicate meaningful calibration.

---

## Transparency Label Design

### High-Confidence AI (confidence ≥ 0.70)

> "Likely AI-generated — Our analysis found strong patterns consistent with machine-written text, including uniform structure and phrasing typical of AI tools. We're confident in this assessment."

### Uncertain (confidence 0.40 – 0.69)

> "Attribution unclear — This content shows mixed signals, and we can't confidently say whether it was written by a person or generated by AI. We're sharing this honestly rather than guessing."

### High-Confidence Human (confidence < 0.40)

> "Likely human-written — Our analysis found natural variation in style and structure typical of original human creative work. We're confident this was not generated by AI."

---

## Appeals Workflow

**Who can appeal:** Any creator who received a classification they disagree with, identified by `content_id` from their submission response.

**Required information:** `content_id` and `creator_reasoning` (free-text explanation of why they believe the classification is wrong).

**System actions on appeal:**
1. Look up the content record by `content_id`; return 404 if not found.
2. Update content `status` from `classified` to `under_review`.
3. Write a new audit log entry of type `appeal` linked to the original `content_id`, including the creator's reasoning and a timestamp.
4. Return confirmation with updated status.

**What a human reviewer would see:** In the audit log, the original classification entry (with both signal scores, confidence, and label) appears alongside a subsequent appeal entry containing the creator's reasoning, timestamp, and `under_review` status. The reviewer can compare signal scores against the creator's explanation before making a manual determination.

---

## Anticipated Edge Cases

### 1. Formal human academic writing

A peer-reviewed abstract or policy brief with consistent sentence structure and domain jargon may score high on stylometric uniformity and moderate-high on the LLM signal. **Expected behavior:** confidence lands in the uncertain band (0.40–0.69), triggering the "Attribution unclear" label rather than falsely labeling it AI-generated.

### 2. Poetry with deliberate repetition

A poem that repeats phrases ("the sea, the sea, the endless sea") will have low type-token ratio and low sentence length variance — both stylometric indicators of AI. **Expected behavior:** stylometric score may be inflated, but if the LLM recognizes poetic intent, disagreement dampening pulls the combined score toward uncertain. Creator can appeal with reasoning.

### 3. Very short submissions (< 50 words)

Stylometric metrics become unreliable with insufficient tokens. **Expected behavior:** stylometric signal defaults toward 0.5 (neutral), and the LLM signal carries more weight. Label likely reads uncertain.

### 4. Non-native English speakers

Writers who produce grammatically correct but structurally uniform English may score higher on stylometric uniformity. **Expected behavior:** the conservative bias cap prevents high-confidence AI labeling when stylometrics suggest human patterns; uncertain label is shown, and appeals pathway is available.

---

## AI Tool Plan

### Milestone 3 — Submission Endpoint + First Signal

**Spec sections provided:** Detection Signals (Signal 1), Architecture diagram, API Surface table.

**Request:** Generate Flask app skeleton with `POST /submit` route stub, SQLite audit log setup, `GET /log` endpoint, and the Groq LLM signal function with structured prompt returning a 0–1 score.

**Verification:** Test the LLM signal function independently with 2–3 text samples. Confirm `POST /submit` returns JSON with `content_id`, `attribution`, `confidence`, and `label`. Verify audit log entries appear via `GET /log`.

### Milestone 4 — Second Signal + Confidence Scoring

**Spec sections provided:** Detection Signals (Signal 2), Uncertainty Representation (thresholds + combining formula), Architecture diagram.

**Request:** Generate stylometric heuristics function (sentence length variance, TTR, punctuation density) and confidence scoring logic that combines both signals per the spec formula.

**Verification:** Run 4 test inputs (clearly AI, clearly human, two borderline). Print individual signal scores and combined confidence. Confirm scores vary meaningfully and map to three label categories.

### Milestone 5 — Production Layer

**Spec sections provided:** Transparency Label Design (all three variants), Appeals Workflow, Architecture diagram.

**Request:** Generate label mapping function using exact label text from spec, `POST /appeal` endpoint with status update and audit logging, and Flask-Limiter rate limiting on `/submit`.

**Verification:** Submit inputs producing each of the three label variants. Submit an appeal and confirm `under_review` status in log. Run rate-limit test (12 rapid requests → 429 after 10).
