THRESHOLD_AI = 0.70
THRESHOLD_HUMAN = 0.40

LLM_WEIGHT = 0.55
STYLO_WEIGHT = 0.45
DISAGREEMENT_THRESHOLD = 0.3


def combine_signals(llm_score: float, stylometric_score: float) -> tuple[float, str]:
    """Combine signal scores into confidence and attribution."""
    base = LLM_WEIGHT * llm_score + STYLO_WEIGHT * stylometric_score

    llm_says_ai = llm_score >= 0.55
    stylo_says_ai = stylometric_score >= 0.55
    llm_says_human = llm_score <= 0.45
    stylo_says_human = stylometric_score <= 0.45
    signals_conflict = (llm_says_ai and stylo_says_human) or (llm_says_human and stylo_says_ai)

    if signals_conflict and abs(llm_score - stylometric_score) > DISAGREEMENT_THRESHOLD:
        base = base * 0.7 + 0.5 * 0.3

    if llm_score > 0.7 and stylometric_score < 0.4:
        base = min(base, 0.65)

    if llm_says_ai and stylo_says_ai:
        base = min(1.0, base + 0.04)

    confidence = max(0.0, min(1.0, base))

    if confidence >= THRESHOLD_AI:
        attribution = "likely_ai"
    elif confidence < THRESHOLD_HUMAN:
        attribution = "likely_human"
    else:
        attribution = "uncertain"

    return round(confidence, 3), attribution
