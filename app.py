import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import get_content, get_log_entries, init_db, log_appeal, save_content, update_status
from labels import generate_label
from scoring import combine_signals
from signals.llm_signal import run_llm_signal
from signals.stylometric_signal import run_stylometric_signal

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

init_db()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True)
    if not data or "text" not in data or "creator_id" not in data:
        return jsonify({"error": "Missing required fields: text, creator_id"}), 400

    text = data["text"].strip()
    creator_id = data["creator_id"]

    if not text:
        return jsonify({"error": "text cannot be empty"}), 400

    content_id = str(uuid.uuid4())

    llm_score = run_llm_signal(text)
    stylometric_score = run_stylometric_signal(text)
    confidence, attribution = combine_signals(llm_score, stylometric_score)
    label = generate_label(confidence, attribution)

    save_content(
        content_id=content_id,
        creator_id=creator_id,
        text=text,
        attribution=attribution,
        confidence=confidence,
        llm_score=round(llm_score, 3),
        stylometric_score=round(stylometric_score, 3),
        label=label,
    )

    return jsonify(
        {
            "content_id": content_id,
            "attribution": attribution,
            "confidence": confidence,
            "label": label,
            "signal_scores": {
                "llm_score": round(llm_score, 3),
                "stylometric_score": round(stylometric_score, 3),
            },
            "status": "classified",
        }
    )


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True)
    if not data or "content_id" not in data or "creator_reasoning" not in data:
        return jsonify({"error": "Missing required fields: content_id, creator_reasoning"}), 400

    content_id = data["content_id"]
    reasoning = data["creator_reasoning"].strip()

    if not reasoning:
        return jsonify({"error": "creator_reasoning cannot be empty"}), 400

    content = get_content(content_id)
    if not content:
        return jsonify({"error": f"Content not found: {content_id}"}), 404

    update_status(content_id, "under_review")
    log_appeal(content_id, content["creator_id"], reasoning)

    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Your appeal has been received and is under review.",
        }
    )


@app.route("/log", methods=["GET"])
def audit_log():
    entries = get_log_entries()
    return jsonify({"entries": entries})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5001)
