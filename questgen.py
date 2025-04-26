# streamlit_app.py
# ───────────────────────────────────────────────────────────
"""
Paste ANY plain-text question block.  GPT-4o will:
• Clean grammar / phrasing
• Find stem + five options (A–E)  ← NEW: 5 options
• Insert full-text correct_answer
• Write ≤80-word explanation & difficulty
• Return a Supabase-ready JSON file
"""

import json
from datetime import datetime, timezone

import openai
import streamlit as st

# ──────────────── GPT function-calling schema ──────────────── #
SCHEMA = {
    "name": "mcq_batch",
    "description": "Return an array of MCQs in strict order.",
    "parameters": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_text": {"type": "string"},
                        "option_a": {"type": "string"},
                        "option_b": {"type": "string"},
                        "option_c": {"type": "string"},
                        "option_d": {"type": "string"},
                        "option_e": {"type": "string"},          # ← NEW
                        "correct_answer": {"type": ["string", "null"]},
                        "explanation_text": {"type": "string"},
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                        },
                        "created_at": {"type": "string"},
                    },
                    "required": [
                        "question_text",
                        "option_a",
                        "option_b",
                        "option_c",
                        "option_d",
                        "option_e",                              # ← NEW
                        "correct_answer",
                        "explanation_text",
                        "difficulty",
                        "created_at",
                    ],
                },
            }
        },
        "required": ["questions"],
    },
}

LETTER_TO_FIELD = {
    "A": "option_a",
    "B": "option_b",
    "C": "option_c",
    "D": "option_d",
    "E": "option_e",         # ← NEW
}

# ──────────────── Streamlit UI ──────────────── #
st.title("🧠 MCQ → Supabase JSON (5-option GPT pipeline)")

q_raw = st.text_area(
    "Question block (any layout; GPT will tidy and extract):",
    height=300,
)

a_raw = st.text_area(
    "Answer key (optional – e.g. 1. C  2. A  …):",
    height=100,
)

if st.button("Generate JSON"):
    if not q_raw.strip():
        st.error("Please paste some questions first.")
        st.stop()

    # ───── Prompt messages ─────
    system_msg = (
        "You are an expert medical-education content formatter.\n"
        "For EVERY question produce FIVE options labelled A–E.\n"
        "Exactly ONE must be correct; E should be an additional plausible but incorrect distractor.\n"
        "Rules:\n"
        "• Preserve medical accuracy – if unsure set correct_answer null and explain.\n"
        "• Explanations ≤80 words.\n"
        "• difficulty = easy / medium / hard.\n"
        "• created_at must be empty string.\n"
        "• Keep the same question order.\n"
    )

    user_msg = "QUESTIONS:\n" + q_raw.strip()
    if a_raw.strip():
        user_msg += "\n\nANSWERS:\n" + a_raw.strip()

    openai.api_key = st.secrets["openai_api_key"]

    with st.spinner("GPT-4o is structuring your questions…"):
        rsp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            functions=[SCHEMA],
            function_call={"name": "mcq_batch"},
            temperature=0.2,
        )

    # ───── Grab JSON from function call ─────
    try:
        content = rsp.choices[0].message.function_call.arguments
        data = json.loads(content)["questions"]
    except Exception as err:  # noqa: BLE001
        st.error(f"Failed to parse GPT response: {err}")
        st.stop()

    # ───── Stamp created_at ─────
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for q in data:
        if q["created_at"] == "":
            q["created_at"] = stamp

    # ───── Download + preview ─────
    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode()
    st.download_button(
        "📥 Download mcq_output.json",
        json_bytes,
        file_name="mcq_output.json",
        mime="application/json",
    )
    st.success(f"Generated {len(data)} records!")
    st.code(json.dumps(data[:2], indent=2, ensure_ascii=False) + ("\n…"), language="json")
