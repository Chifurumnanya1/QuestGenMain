# streamlit_mcq_processor.py

import streamlit as st
from google import genai

# — INSTALLATION —
# pip install streamlit google-genai

# — CONFIGURATION —
# Create .streamlit/secrets.toml:
# [defaults]
# GEMINI_API_KEY = "<YOUR_GEMINI_API_KEY>"

# Initialize the Gemini client
client = genai.Client(
    vertexai=True,
    api_key=st.secrets["defaults"]["GEMINI_API_KEY"]
)

st.title("MCQ → JSON with Explanations")

block = st.text_area(
    "Paste your full questions + SECTION A: ANSWER key block here:",
    height=400
)

if st.button("Generate JSON"):
    prompt = f"""
You are given a block of text containing:
1) Numbered multiple‐choice questions with options labeled (a), (b), (c), (d), (e).
2) A “SECTION A: OBJECTIVE ANSWER” key listing mappings like “1C”, “2A”, …, “120B”.

Parse each question into a JSON object with these exact keys:
- question_text: the question stem.
- option_a, option_b, option_c, option_d, option_e: the full text of each option.
- correct_answer: the letter (A–E) that matches the answer key, or null if the key letter doesn't match any option.
- explanation_text: one concise sentence explaining why the correct answer is right (or noting “Answer key mismatch – please review.” if null).
- difficulty: set to “medium” for all.
- created_at: leave as an empty string.

Output ONLY a JSON array of these objects, with no surrounding commentary.

Text block:
{block}
"""
    with st.spinner("Calling Gemini..."):
        response = client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=prompt,
        )
    json_output = response.text

    st.subheader("Generated JSON")
    st.code(json_output, language="json")

    st.download_button(
        "Download JSON",
        data=json_output,
        file_name="questions.json",
        mime="application/json"
    )
