import streamlit as st
from openai import OpenAI
from datetime import datetime
from io import StringIO
import pandas as pd

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Updated SYSTEM PROMPT
SYSTEM_PROMPT = """
You are an expert MCQ formatter and CSV generator.
You will receive messy MCQs and answer keys.

For each MCQ:
- Correct grammar and structure.
- Create four options A, B, C, D.
- Invent an extra wrong option E (different from the correct answer).
- Match the correct answer using the **full exact option text**.
- Generate a short 1-2 line explanation why the correct option is correct.
- Set difficulty as "easy".
- Leave created_at as blank.

Output ONLY clean CSV text with this exact heading:

id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at

Important Rules:
- Surround EVERY text field (question, options, explanation) with double quotes ("...") to protect commas.
- Escape any inner double quotes properly.
- Start id from 1, 2, 3, upward.
- No JSON, no markdown, no explanation around the CSV. Only raw CSV data.
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
st.set_page_config(page_title="MCQ to CSV Generator", page_icon="🧠", layout="wide")

st.title("🧠 MCQ Cleaner and CSV Generator")
st.write("Paste messy MCQs and answers, and get a clean downloadable CSV!")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300, placeholder="Paste your questions and options here...")

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys", height=100, placeholder="Example: 1.B 2.A 3.C")

if st.button("🚀 Generate CSV"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        user_prompt = f"Here are the MCQs:\n{raw_mcqs}\n\nHere are the correct answers:\n{answer_keys}"
        with st.spinner("🧠 Processing with OpenAI..."):
            csv_output = call_openai(user_prompt)

        try:
            # Try reading the CSV output safely
            csv_buffer = StringIO(csv_output)
            df = pd.read_csv(csv_buffer)
            
            st.success("✅ MCQs cleaned and formatted!")
            st.download_button(
                label="📥 Download Cleaned MCQs as CSV",
                data=csv_output,
                file_name=f"mcqs_cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            st.dataframe(df)  # Show preview table inside Streamlit

        except Exception as e:
            st.error(f"⚠️ Error reading the generated CSV: {e}")
            st.code(csv_output)
