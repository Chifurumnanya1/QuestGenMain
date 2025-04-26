import streamlit as st
import openai
from openai import OpenAI
from datetime import datetime

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# System Prompt
SYSTEM_PROMPT = """
You are an expert MCQ formatter.
You will receive messy MCQ questions and answer keys.
Your job is to:
- Correct spelling and grammar mistakes.
- Reframe unclear questions without changing their meaning.
- Group each question nicely:
    - Numbered properly.
    - Each with options A, B, C, D.
    - Show the correct answer clearly.
Do not add any intro or outro text, only clean MCQs.
After each question, show "**Correct Answer: X. (Option text)**" exactly.
"""

def call_openai(user_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",  # You can also use "gpt-4-turbo" or "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1,
        max_tokens=4000
    )
    return response.choices[0].message.content

# Streamlit App
st.set_page_config(page_title="MCQ Cleaner AI", page_icon="🧠", layout="wide")

st.title("🧠 MCQ Formatter using OpenAI")
st.write("Paste your messy MCQ text and answers, AI will clean it for you!")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300, help="Paste your questions and options here.")

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys (e.g., 1.B 2.A 3.C)", height=100)

if st.button("🚀 Clean and Format with AI"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        user_prompt = f"Here are the MCQs:\n{raw_mcqs}\n\nHere are the correct answers:\n{answer_keys}"
        with st.spinner("Talking to OpenAI..."):
            cleaned_mcqs = call_openai(user_prompt)
        st.success("✅ MCQs cleaned successfully!")
        st.download_button(
            label="📥 Download Cleaned MCQs",
            data=cleaned_mcqs,
            file_name=f"cleaned_mcqs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )
        st.code(cleaned_mcqs, language="markdown")
