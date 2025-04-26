import streamlit as st
from openai import OpenAI
from datetime import datetime

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# System Prompt (updated)
SYSTEM_PROMPT = """
You are an expert MCQ formatter and explainer.
You will receive messy MCQ questions and answer keys.
Your job is to:
- Correct spelling, grammar, and structure.
- Reframe unclear questions without changing meaning.
- Group questions properly:
    - Number them.
    - List options A, B, C, D.
    - State the correct answer clearly.
    - After each correct answer, write a short explanation (2-3 sentences) explaining why the correct option is right.
Format each question like this:
---
## Question 1
Question text
A. Option A
B. Option B
C. Option C
D. Option D
**Correct Answer: X. (option text)**

**Explanation:**  
(Your brief explanation here.)
---
Do not add any introduction or conclusion outside the MCQs.
"""

def call_openai(user_prompt):
    response = client.chat.completions.create(
        model="gpt-4o",  
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=4000
    )
    return response.choices[0].message.content

# Streamlit App
st.set_page_config(page_title="MCQ Formatter + Explanation", page_icon="🧠", layout="wide")

st.title("🧠 MCQ Cleaner + Explanation Generator (OpenAI)")
st.write("Paste your messy MCQs and answers, get clean, explained questions!")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300)

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys (e.g., 1.B 2.A 3.C)", height=100)

if st.button("🚀 Clean and Generate MCQs + Explanations"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        user_prompt = f"Here are the MCQs:\n{raw_mcqs}\n\nHere are the correct answers:\n{answer_keys}"
        with st.spinner("Talking to OpenAI..."):
            cleaned_mcqs = call_openai(user_prompt)
        st.success("✅ MCQs generated with explanations!")
        st.download_button(
            label="📥 Download Cleaned MCQs",
            data=cleaned_mcqs,
            file_name=f"cleaned_mcqs_with_explanations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain"
        )
        st.code(cleaned_mcqs, language="markdown")
