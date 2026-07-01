# Provenance Guard

A backend system for creative sharing platforms to classify submitted text, score confidence in that classification, surface transparency labels to readers, and handle appeals from creators who believe they've been misclassified.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
pip install -r requirements.txt

# Copy .env.example to .env and add your GROQ_API_KEY
cp .env.example .env

python app.py                        # runs on http://127.0.0.1:5001
```

> **Note:** macOS often reserves port 5000 for AirPlay. This app runs on **port 5001** and binds to `127.0.0.1`. Use `http://127.0.0.1:5001` in curl commands (not `localhost:5000`).

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/submit` | POST | Submit text for attribution analysis |
| `/appeal` | POST | Contest a classification |
| `/log` | GET | View structured audit log entries |
| `/health` | GET | Health check |

---

## Architecture Overview

When a creator submits content, it flows through the following path:

1. **POST /submit** receives `{text, creator_id}` and assigns a unique `content_id`.
2. **Signal 1 (Groq LLM)** assesses semantic and stylistic coherence holistically, returning `llm_score` (0–1).
3. **Signal 2 (Stylometric heuristics)** computes structural statistics (sentence length variance, type-token ratio, template phrase density), returning `stylometric_score` (0–1).
4. **Scoring engine** combines both signals with weighted averaging, directional conflict dampening, and a conservative cap to reduce false positives.
5. **Label generator** maps the combined confidence score to one of three plain-language transparency labels.
6. **Audit log (SQLite)** records the full decision — both signal scores, confidence, attribution, label, and timestamp.
7. **JSON response** returns `content_id`, `attribution`, `confidence`, `label`, `signal_scores`, and `status`.

If a creator disagrees, **POST /appeal** accepts `{content_id, creator_reasoning}`, updates the content status to `under_review`, and appends a linked appeal entry to the audit log.

See `planning.md` for the full architecture diagram and design rationale.

---

## Detection Signals

### Signal 1: LLM Semantic Assessment (Groq — llama-3.3-70b-versatile)

**What it measures:** Whether the text reads like polished, template-driven AI prose or authentic human expression with idiosyncrasies — including hedging phrases, balanced sentence structures, and lack of personal voice.

**Why I chose it:** LLMs can evaluate holistic writing quality in ways that pure statistics cannot. A casual blog post with irregular rhythm and colloquialisms looks fundamentally different from AI-generated corporate prose, even when both are grammatically correct.

**What it misses:** Heavily edited AI output, formal human academic writing, and non-native English speakers who write in a structured style may score higher than intended. The model can also reflect its own biases about what "AI writing" looks like.

### Signal 2: Stylometric Heuristics (Pure Python)

**What it measures:** Structural statistical properties:
- **Sentence length variance** — AI text tends toward uniform sentence lengths; human writing varies more.
- **Type-token ratio** — ratio of unique words to total words; AI text often repeats vocabulary.
- **Template phrase density** — frequency of phrases like "it is important to note" and "furthermore."
- **Transition word ratio** — density of words like "moreover" and "consequently."
- **Punctuation uniformity** — consistent punctuation patterns across sentences.

**Why I chose it:** These metrics are genuinely independent from the LLM signal — one is semantic, one is structural. AI models optimize for readability and consistency, producing statistically smoother text. Combining both gives more informative results than either alone.

**What it misses:** Deliberately stylized poetry with repetition, very short texts (insufficient data), and human writers who produce highly polished, uniform prose (e.g., technical documentation or academic abstracts).

---

## Confidence Scoring

### Combining Signals

```
base_confidence = (0.55 × llm_score) + (0.45 × stylometric_score)
```

**Directional conflict dampening:** When one signal says AI (≥ 0.55) and the other says human (≤ 0.45), the score is pulled toward 0.5. This reflects the false-positive asymmetry — conflicting evidence should produce uncertainty, not a confident wrong label.

**Conservative cap:** When the LLM strongly says AI (> 0.7) but stylometrics strongly say human (< 0.4), confidence is capped at 0.65 to protect creators from high-confidence false positives.

**Agreement boost:** When both signals agree on AI (both ≥ 0.55), a small +0.04 boost is applied.

### Thresholds

| Confidence Range | Attribution | Label |
|-----------------|-------------|-------|
| ≥ 0.70 | `likely_ai` | High-confidence AI |
| 0.40 – 0.69 | `uncertain` | Uncertain |
| < 0.40 | `likely_human` | High-confidence human |

The uncertain band is intentionally wide (30 percentage points) to avoid forcing binary judgments on borderline content.

### Validation

I tested four deliberately chosen inputs spanning the confidence range. Scores cluster at extremes for clear cases and land in the uncertain band for borderline content:

**Example 1 — High-confidence AI (confidence: 0.704)**

```json
{
  "attribution": "likely_ai",
  "confidence": 0.704,
  "signal_scores": { "llm_score": 0.9, "stylometric_score": 0.464 }
}
```

Text: *"Artificial intelligence represents a transformative paradigm shift… Furthermore, stakeholders across various sectors must collaborate… In conclusion, responsible innovation remains paramount."*

**Example 2 — High-confidence human (confidence: 0.182)**

```json
{
  "attribution": "likely_human",
  "confidence": 0.182,
  "signal_scores": { "llm_score": 0.1, "stylometric_score": 0.282 }
}
```

Text: *"ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it…"*

The 0.52-point gap between these examples (0.704 vs 0.182) demonstrates meaningful score variation, not a constant output.

---

## Transparency Labels

The label text changes based on confidence level — wording is different, not just the number.

| Category | Confidence | Exact Label Text |
|----------|-----------|------------------|
| High-confidence AI | ≥ 0.70 | "Likely AI-generated — Our analysis found strong patterns consistent with machine-written text, including uniform structure and phrasing typical of AI tools. We're confident in this assessment." |
| Uncertain | 0.40 – 0.69 | "Attribution unclear — This content shows mixed signals, and we can't confidently say whether it was written by a person or generated by AI. We're sharing this honestly rather than guessing." |
| High-confidence human | < 0.40 | "Likely human-written — Our analysis found natural variation in style and structure typical of original human creative work. We're confident this was not generated by AI." |

---

## Rate Limiting

The `/submit` endpoint is rate-limited via Flask-Limiter:

```
10 per minute; 100 per day
```

**Reasoning:**
- **10/minute:** A writer submitting their own work might paste 2–3 drafts in quick succession while editing, then pause. Ten per minute allows burst editing without blocking normal use, but stops a script from flooding the system (each submission triggers two detection signals, including a Groq API call).
- **100/day:** A prolific creator publishing several pieces daily would rarely exceed 20–30 submissions. One hundred per day allows heavy legitimate use while capping abuse from a single IP over a full day.

### Rate Limit Evidence

Running 12 rapid submissions on a freshly started server (10/minute limit):

```
200
200
200
200
200
200
200
200
200
200
429
429
```

The first 10 requests succeed; requests 11 and 12 return **HTTP 429**.

---

## Audit Log

Every classification and appeal is stored in a structured SQLite audit log, retrievable via `GET /log`.

Sample output (abbreviated):

```json
{
  "entries": [
    {
      "entry_type": "appeal",
      "content_id": "a20c80a3-eeb3-43f8-bcb3-a7f9af3ba2b2",
      "creator_id": "demo-user-1",
      "timestamp": "2026-07-01T05:16:41.784491+00:00",
      "attribution": "likely_ai",
      "confidence": 0.704,
      "llm_score": 0.9,
      "stylometric_score": 0.464,
      "status": "under_review",
      "appeal_reasoning": "I wrote this myself from personal experience..."
    },
    {
      "entry_type": "classification",
      "content_id": "64f5fcfd-e224-4071-b1af-21cee053a987",
      "timestamp": "2026-07-01T05:16:41.761522+00:00",
      "attribution": "uncertain",
      "confidence": 0.508,
      "llm_score": 0.7,
      "stylometric_score": 0.282,
      "status": "classified"
    },
    {
      "entry_type": "classification",
      "content_id": "2c94f2df-6b6d-429d-b79d-dc35746d680f",
      "timestamp": "2026-07-01T05:16:41.321595+00:00",
      "attribution": "likely_human",
      "confidence": 0.182,
      "llm_score": 0.1,
      "stylometric_score": 0.282,
      "status": "classified"
    }
  ]
}
```

Run `./run_demo.sh` to reproduce submissions, an appeal, and the audit log locally.

For rate-limit evidence, restart the server and run `./run_rate_limit_test.sh` before any other requests.

---

## Appeals Workflow

Creators contest a classification via `POST /appeal`:

```bash
curl -s -X POST http://127.0.0.1:5001/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "YOUR-CONTENT-ID", "creator_reasoning": "I wrote this myself..."}'
```

The system:
1. Looks up the content by `content_id`
2. Updates status from `classified` → `under_review`
3. Logs the appeal with the original classification scores and the creator's reasoning
4. Returns confirmation

A human reviewer sees both the original classification entry and the appeal entry in the audit log, with full signal scores for comparison.

---

## Known Limitations

**Formal academic or policy writing from human experts** is the most likely misclassification scenario. Text like peer-reviewed abstracts or central-bank commentary has consistent sentence structure, domain jargon, and measured tone — properties that score high on stylometric uniformity and moderate-high on the LLM signal. In testing, a monetary-policy excerpt scored 0.508 (uncertain) with `llm_score: 0.7` and `stylometric_score: 0.282`. The system avoids a high-confidence AI label thanks to the conservative cap, but the LLM signal alone would push toward false positives. Creators in this category would need to use the appeals workflow.

---

## Spec Reflection

**How the spec helped:** The planning requirement to define thresholds *before* implementation forced me to think about what 0.6 means to a user, not just as a number. Writing out the three label variants in `planning.md` before coding meant the label generator had exact text to implement against, rather than placeholder strings I'd rewrite later.

**Where implementation diverged:** I originally set the high-confidence AI threshold at 0.72, but after testing with real Groq responses, clearly AI-generated text consistently scored 0.65–0.71 due to directional conflict dampening when stylometrics lagged behind the LLM. I lowered the threshold to 0.70 so that strong agreement between signals (LLM 0.9, stylometric 0.46) produces a high-confidence AI label, while borderline cases still land in the uncertain band. I also changed disagreement dampening from "any large gap" to "directional conflict only" — two signals that both lean AI should not be penalized just because they disagree on degree.

---

## AI Usage

### Instance 1: Flask App Skeleton and LLM Signal (Milestone 3)

**Prompt:** I provided the detection signals section and architecture diagram from `planning.md` and asked the AI to generate a Flask app skeleton with `POST /submit`, SQLite audit log, `GET /log`, and the Groq LLM signal function returning a 0–1 score.

**Output:** The AI produced a working Flask structure with route stubs, a Groq client wrapper, and SQLite schema.

**What I revised:** I split the monolithic output into separate modules (`signals/`, `scoring.py`, `labels.py`, `audit_log.py`) for clarity. I rewrote the LLM prompt to request strict JSON output and added a regex fallback parser for malformed responses. I also added a keyword-based fallback heuristic for development without an API key, which I kept as a safety net.

### Instance 2: Stylometric Signal and Confidence Scoring (Milestone 4)

**Prompt:** I provided the detection signals, uncertainty representation, and architecture diagram sections and asked for the stylometric heuristics function and confidence scoring logic matching my spec's combining formula.

**Output:** The AI generated sentence-length variance and type-token ratio functions plus a weighted combiner.

**What I revised:** The initial stylometric signal only used three metrics and under-scored obvious AI template prose. I added template-phrase detection and transition-word scoring based on my edge-case analysis in `planning.md`. I also changed the disagreement dampening from blind gap detection to directional conflict only, and added the conservative false-positive cap — the AI's original combiner treated all disagreement equally, which pulled clearly AI text into the uncertain band too aggressively.

### Instance 3: Production Layer — Labels, Appeals, Rate Limiting (Milestone 5)

**Prompt:** I provided the transparency label variants, appeals workflow, and architecture diagram and asked for a label mapping function, `POST /appeal` endpoint, and Flask-Limiter setup on `/submit`.

**Output:** The AI generated a threshold-based label function, appeal route with status update, and limiter decorator.

**What I revised:** I copied the exact label strings from `planning.md` rather than using the AI's paraphrased versions (which included jargon like "classifier confidence"). I wired the appeal endpoint to write a separate `appeal` entry type in the audit log rather than overwriting the original classification row. I also changed the default port to 5001 after discovering macOS AirPlay occupies port 5000.

---

## Project Structure

```
├── app.py                  # Flask routes and rate limiting
├── audit_log.py            # SQLite storage and log retrieval
├── scoring.py              # Signal combination and thresholds
├── labels.py               # Transparency label text
├── signals/
│   ├── llm_signal.py       # Groq LLM assessment
│   └── stylometric_signal.py  # Statistical heuristics
├── planning.md             # Architecture and design spec
├── run_demo.sh             # Submissions, appeal, and audit log demo
├── run_rate_limit_test.sh  # Rate limit test (run on fresh server)
├── requirements.txt
└── .env.example
```
