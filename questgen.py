import streamlit as st
import openai, json, datetime as dt, re

# ──────────────────────────────────────────────────────────────
# API Key Setup
# ──────────────────────────────────────────────────────────────
openai.api_key = st.secrets["openai_api_key"]
if not openai.api_key:
    st.error("API key missing in Streamlit Secrets")
    st.stop()

# ──────────────────────────────────────────────────────────────
# Streamlit Page Config + Orange Border Style
# ──────────────────────────────────────────────────────────────
st.set_page_config("MCQ Generator", "📚", layout="centered")
st.markdown(
    """<style>.css-1cpxqw2{border:2px solid #FFA500;border-radius:5px;padding:8px}</style>""",
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────
# Extract a topic title from the passage
# ──────────────────────────────────────────────────────────────
def extract_topic(text):
    prompt = "Summarize the main topic of the text below in 3–5 words (no full sentence):\n\n" + text
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user", "content": prompt}],
        temperature=0.2,
    )
    topic = response.choices[0].message.content.strip()
    # Convert to a safe filename slug
    slug = re.sub(r"[^\w\s-]", "", topic)          # remove punctuation
    slug = re.sub(r"\s+", "_", slug).lower()       # spaces to underscores
    return slug or "untitled_topic"

# ──────────────────────────────────────────────────────────────
# Generate MCQs as JSON with OpenAI
# ──────────────────────────────────────────────────────────────
def make_json(text, n):
    sys = (
        "Return ONLY valid JSON — an array of objects with keys: "
        "question_text, option_a to option_e, correct_answer (the key name like option_a), "
        "explanation_text, difficulty (easy|medium|hard), and created_at (leave as empty string)."
    )
    user = f"Generate {n} five-option MCQs from the text:\n\n{text}"
    out = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"system", "content": sys}, {"role":"user", "content": user}],
        temperature=0.3,
    ).choices[0].message.content.strip()
    return out

# ──────────────────────────────────────────────────────────────
# Normalize correct_answer to actual string instead of option_a
# ──────────────────────────────────────────────────────────────
def normalize_correct_answers(data):
    for q in data:
        key = q["correct_answer"]
        if key in ["option_a", "option_b", "option_c", "option_d", "option_e"]:
            q["correct_answer"] = q.get(key, "")
    return data

# ──────────────────────────────────────────────────────────────
# Streamlit UI
# ──────────────────────────────────────────────────────────────
st.title("Cesium MCQ Generator 🚀")

source = st.text_area("Input Text", height=200)
count  = st.number_input("Number of questions", 1, 50, 10)

if st.button("Generate JSON"):
    if not source.strip():
        st.warning("Please enter some source text.")
        st.stop()

    st.info("Extracting topic and generating MCQs… ⏳")

    # ➤ Get topic
    topic_slug = extract_topic(source)

    # ➤ Generate questions
    raw = make_json(source, count)

    # ➤ Validate JSON
    if not raw.strip():
        st.error("OpenAI returned an empty response. Please try again.")
        st.stop()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"OpenAI returned invalid JSON:\n{e}\n\nRaw output:\n{raw}")
        st.stop()

    # ➤ Normalize correct_answer to real string
    data = normalize_correct_answers(data)

    # ➤ Generate filename: mcqs_topic_slug_YYYYMMDD_HHMMSS.json
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"mcqs_{topic_slug}_{timestamp}.json"

    # ➤ Save file
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # ➤ Preview + Download
    st.success(f"Done! File saved as **{filename}**")
    st.json(data, expanded=False)

    with open(filename, "rb") as f:
        st.download_button(f"Download {filename}", f, filename, "application/json")
