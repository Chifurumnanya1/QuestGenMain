# app.py
import streamlit as st
import openai, json, datetime as dt
import re
import os
# ─────────────────────────────────────────────────────────
# 1.  API key
# ─────────────────────────────────────────────────────────
# Try lowercase first (matches your secrets), then env‑var fallback
openai_api_key = st.secrets.get("openai_api_key") or os.getenv("OPENAI_API_KEY")

if not openai_api_key:
    st.error(
        "OpenAI key not found.\n"
        "Add `openai_api_key` to Streamlit Secrets or set the OPENAI_API_KEY env var."
    )
    st.stop()

openai.api_key = openai_api_key

# ─────────────────────────────────────────────────────────
# 2.  Page config + style
# ─────────────────────────────────────────────────────────
st.set_page_config("Text ➜ MCQ JSON Generator", "📚", layout="centered")
st.markdown(
    """<style>.css-1cpxqw2{border:2px solid #FFA500;border-radius:5px;padding:8px}</style>""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────
# 3.  Prompt templates
# ─────────────────────────────────────────────────────────
SCHEMA = """
{
  "question_text": "string",
  "option_a": "string",
  "option_b": "string",
  "option_c": "string",
  "option_d": "string",
  "option_e": "string",
  "correct_answer": "string",
  "explanation_text": "string",
  "difficulty": "easy|medium|hard",
  "created_at": ""
}
""".strip()

SYSTEM_PROMPT = (
    "You are an MCQ generator.\n"
    "Return ONLY valid JSON — an array of objects. Every object must match exactly this schema:\n"
    + SCHEMA +
    "\nDo NOT wrap the JSON in markdown or add any extra keys."
)

def build_user_prompt(text: str, n_q: int) -> str:
    return (
        f"Generate {n_q} five‑option MCQs from the passage below. "
        "The correct_answer field must equal one of option_a‑e verbatim.\n\n"
        '"""' + text + '"""'
    )

# ─────────────────────────────────────────────────────────
# 4.  Streamlit UI
# ─────────────────────────────────────────────────────────
st.title("Text ➜ MCQ JSON Generator 🚀")

source_text = st.text_area("Paste textbook content", height=220)
num_qs      = st.number_input("How many MCQs?", 1, 50, 10)
topic_field = st.text_input("File topic (used as filename prefix)")

if st.button("Generate JSON"):
    if not source_text.strip():
        st.warning("Please paste some source text."); st.stop()
    if not topic_field.strip():
        st.warning("Please enter a topic for the filename."); st.stop()

    # ---------------- OpenAI call ----------------
    st.info("Generating MCQs … please wait ⏳")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_prompt(source_text, num_qs)},
        ],
        temperature=0.2,
    ).choices[0].message.content.strip()

    # ---------------- Validate JSON ----------------
    if not response:
        st.error("OpenAI returned an empty response."); st.stop()

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        st.error("Could not parse JSON from OpenAI:\n\n" + response); st.stop()

    # replace placeholders like "option_b" with the actual answer string
    for q in data:
        key = q.get("correct_answer", "")
        if key in ["option_a", "option_b", "option_c", "option_d", "option_e"]:
            q["correct_answer"] = q.get(key, "")

    # ---------------- Build filename ----------------
    # Keep only filesystem‑safe characters from topic input
    safe_topic = re.sub(r"[^\w\-. ]", "_", topic_field.strip())
    timestamp  = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename   = f"{safe_topic}_{timestamp}.json"

    # ---------------- Write file & serve ----------------
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    st.success(f"Created **{filename}**")
    st.json(data, expanded=False)

    with open(filename, "rb") as f:
        st.download_button("Download JSON", f, file_name=filename,
                           mime="application/json")
