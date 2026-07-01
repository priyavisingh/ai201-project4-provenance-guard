import re
import statistics

AI_PHRASES = [
    "it is important to note",
    "furthermore",
    "in conclusion",
    "paradigm shift",
    "stakeholders",
    "it is equally essential",
    "transformative",
    "various sectors",
    "it is worth noting",
    "in today's",
    "plays a crucial role",
    "multifaceted",
]

TRANSITION_WORDS = {
    "furthermore", "moreover", "additionally", "however", "therefore",
    "consequently", "nevertheless", "thus", "hence", "accordingly",
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+", text)
    return [s.strip() for s in parts if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _sentence_length_variance_score(sentences: list[str]) -> float:
    """Low variance → higher AI likelihood."""
    if len(sentences) < 2:
        return 0.5
    lengths = [len(s.split()) for s in sentences]
    variance = statistics.variance(lengths) if len(lengths) > 1 else 0
    # Normalize: variance < 5 is very uniform (AI-like), > 30 is very varied (human)
    if variance <= 5:
        return 0.85
    if variance >= 30:
        return 0.15
    return 1.0 - (variance - 5) / 25 * 0.7


def _type_token_ratio_score(words: list[str]) -> float:
    """Low TTR → higher AI likelihood."""
    if not words:
        return 0.5
    ttr = len(set(words)) / len(words)
    if ttr <= 0.45:
        return 0.8
    if ttr >= 0.75:
        return 0.2
    return 0.8 - (ttr - 0.45) / 0.3 * 0.6


def _template_phrase_score(text: str) -> float:
    """High density of AI-typical phrases → higher AI likelihood."""
    lower = text.lower()
    hits = sum(1 for phrase in AI_PHRASES if phrase in lower)
    words = _words(text)
    if not words:
        return 0.5
    density = hits / max(len(_sentences(text)), 1)
    if density >= 2:
        return 0.9
    if density >= 1:
        return 0.75
    if density == 0:
        return 0.25
    return 0.5


def _transition_word_score(words: list[str]) -> float:
    """Frequent transition words → higher AI likelihood."""
    if not words:
        return 0.5
    count = sum(1 for w in words if w in TRANSITION_WORDS)
    ratio = count / len(words)
    if ratio >= 0.08:
        return 0.85
    if ratio >= 0.04:
        return 0.65
    if ratio == 0:
        return 0.2
    return 0.4


def _punctuation_uniformity_score(text: str) -> float:
    """Uniform punctuation patterns → higher AI likelihood."""
    sentences = _sentences(text)
    if len(sentences) < 2:
        return 0.5
    densities = []
    for s in sentences:
        punct = len(re.findall(r"[,;:—\-]", s))
        densities.append(punct / max(len(s.split()), 1))
    if len(densities) < 2:
        return 0.5
    variance = statistics.variance(densities)
    if variance <= 0.001:
        return 0.75
    if variance >= 0.02:
        return 0.25
    return 0.75 - (variance - 0.001) / 0.019 * 0.5


def run_stylometric_signal(text: str) -> float:
    """Return a score from 0.0 (likely human) to 1.0 (likely AI)."""
    if len(text.split()) < 10:
        return 0.5

    sentences = _sentences(text)
    words = _words(text)

    sl_score = _sentence_length_variance_score(sentences)
    ttr_score = _type_token_ratio_score(words)
    punct_score = _punctuation_uniformity_score(text)
    template_score = _template_phrase_score(text)
    transition_score = _transition_word_score(words)

    return (
        0.25 * sl_score
        + 0.20 * ttr_score
        + 0.15 * punct_score
        + 0.25 * template_score
        + 0.15 * transition_score
    )
