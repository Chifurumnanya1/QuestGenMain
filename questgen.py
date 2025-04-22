# app.py
import streamlit as st
import openai, json, datetime as dt
from slugify import slugify

# ─────────────────────────────────────────────────────────
# 1.  API key (add OPENAI_API_KEY in Streamlit Cloud Secrets)
# ─────────────────────────────────────────────────────────
openai.api_key = st.secrets["OPENAI_API_KEY"]
if not openai.api_key:
    st.error("OPENAI_API_KEY missing in Secrets"); st.stop()

# ─────────────────────────────────────────────────────────
# 2.  Page config + tiny style tweak
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
topic_input = st.text_input("Topic slug (optional)", placeholder="e.g. brachial_plexus")

if st.button("Generate JSON"):
    # Basic checks
    if not source_text.strip():
        st.warning("Please paste some source text first."); st.stop()

    # ---------------- OpenAI call ----------------
    st.info("Calling OpenAI … please wait ⏳")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",           # swap to gpt‑4o if you have access
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
    except json.JSONDecodeError as e:
        st.error("Could not parse JSON from OpenAI:\n\n" + response); st.stop()

    # Ensure correct_answer is the actual answer string
    for q in data:
        key = q.get("correct_answer", "")
        if key in ["option_a", "option_b", "option_c", "option_d", "option_e"]:
            q["correct_answer"] = q.get(key, "")

    # ---------------- Build filename ----------------
    slug = topic_input.strip()
    if not slug:
        # fallback: derive from first 3 words of first question
        slug = slugify(" ".join(data[0]["question_text"].split()[:3])) or "mcqs"
    else:
        slug = slugify(slug)

    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename  = f"{slug}_{timestamp}.json"

    # ---------------- Write file & serve ----------------
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    st.success(f"Created **{filename}**")
    st.json(data, expanded=False)

    with open(filename, "rb") as f:
        st.download_button("Download JSON", f, file_name=filename,
                           mime="application/json")
