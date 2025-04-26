# mcq_formatter.py
import streamlit as st
import openai
import re, json, datetime
from io import StringIO

# ---- CONFIG -----------------------------------------------------------------
st.set_page_config(page_title="MCQ Formatter → JSON", page_icon="🩺")
openai.api_key = st.secrets.get("OPENAI_API_KEY")           # <── add in ☁ or .env
MODEL = "gpt-4o"                                            # or any GPT-4-class model
SYSTEM_PROMPT = """
You are an expert medical-education content formatter.
<insert the long instructions block you supplied verbatim here>
""".strip()

# ---- SIDEBAR ----------------------------------------------------------------
st.sidebar.header("How it works")
st.sidebar.markdown(
"""
1. Paste the raw **QUESTIONS** and **ANSWERS** text ↓  
2. Click **Format with GPT-4o** – the LLM returns tidy blocks.  
3. The app converts those blocks to the JSON list you need.  
4. Download the file and use it anywhere.
"""
)

# ---- INPUTS -----------------------------------------------------------------
st.title("🩺 MCQ Formatter → neat JSON")
qs = st.text_area("Paste the *QUESTIONS* block here:", height=250)
ans = st.text_area("Paste the *ANSWERS* block here:", height=120)

# ---- RUN LLM ----------------------------------------------------------------
if st.button("⚙️ Format with GPT-4o", disabled=not (qs and ans)):
    if not openai.api_key:
        st.error("Missing OpenAI key – add OPENAI_API_KEY to Streamlit secrets.")
        st.stop()

    with st.spinner("Contacting GPT-4o …"):
        user_prompt = f"QUESTIONS:\n{qs}\n\nANSWERS:\n{ans}"
        chat = openai.ChatCompletion.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        formatted = chat.choices[0].message.content.strip()
    st.success("Done! See output below 👇🏾")
    st.code(formatted, language="text")

    # ---- PARSE CLEANED BLOCKS ------------------------------------------------
    blocks = re.split(r"\n\s*\n", formatted)  # blank-line separator
    json_list = []
    now_iso = datetime.datetime.utcnow().isoformat()

    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) != 8 or not lines[0].startswith("##"):
            st.warning("Skipping malformed block:\n" + b)
            continue
        stem = lines[0][2:].strip()
        difficulty = lines[6][2:].strip()        # after %%
        explanation = lines[7][2:].strip()       # after &&
        json_list.append({
            "question_text": stem,
            "difficulty": difficulty,
            "explanation_text": explanation,
            "correct_answer": None,              # or pull from key if desired
            "created_at": now_iso,
        })

    json_str = json.dumps(json_list, indent=2, ensure_ascii=False)
    st.subheader("📄 Generated JSON")
    st.code(json_str, language="json")

    # ---- DOWNLOAD ------------------------------------------------------------
    st.download_button(
        label="💾 Download JSON file",
        data=json_str,
        file_name="formatted_questions.json",
        mime="application/json",
    )

# ---- FOOTER -----------------------------------------------------------------
st.caption("Built with ❤️ & Streamlit • GPT-4o • 2025")
