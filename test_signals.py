#!/usr/bin/env python3
"""Quick test script for signal scoring without running the server."""

from dotenv import load_dotenv

load_dotenv()

from scoring import combine_signals
from signals.llm_signal import run_llm_signal
from signals.stylometric_signal import run_stylometric_signal
from labels import generate_label

TEST_INPUTS = {
    "clearly_ai": (
        "Artificial intelligence represents a transformative paradigm shift in modern society. "
        "It is important to note that while the benefits of AI are numerous, it is equally "
        "essential to consider the ethical implications. Furthermore, stakeholders across "
        "various sectors must collaborate to ensure responsible deployment."
    ),
    "clearly_human": (
        "ok so i finally tried that new ramen place downtown and honestly? "
        "underwhelming. the broth was fine but they put WAY too much sodium in it and "
        "i was thirsty for like three hours after. my friend got the spicy version and "
        "said it was better. probably won't go back unless someone drags me there"
    ),
    "borderline_formal": (
        "The relationship between monetary policy and asset price inflation has been "
        "extensively studied in the literature. Central banks face a fundamental tension "
        "between their mandate for price stability and the unintended consequences of "
        "prolonged low interest rates on equity and real estate valuations."
    ),
    "borderline_edited_ai": (
        "I've been thinking a lot about remote work lately. There are genuine tradeoffs — "
        "flexibility and no commute on one side, isolation and blurred work-life boundaries "
        "on the other. Studies show productivity varies widely by individual and role type."
    ),
}

if __name__ == "__main__":
    for name, text in TEST_INPUTS.items():
        llm = run_llm_signal(text)
        stylo = run_stylometric_signal(text)
        conf, attr = combine_signals(llm, stylo)
        label = generate_label(conf, attr)
        print(f"\n=== {name} ===")
        print(f"  llm_score:          {llm:.3f}")
        print(f"  stylometric_score:  {stylo:.3f}")
        print(f"  confidence:         {conf:.3f}")
        print(f"  attribution:        {attr}")
        print(f"  label:              {label[:60]}...")
