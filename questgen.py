import streamlit as st
import openai
from datetime import datetime
from io import StringIO
import pandas as pd
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# System prompt (PURE CSV version)
SYSTEM_PROMPT = """
You are an expert MCQ formatter.
You will receive messy MCQs and answer keys.
Your job is to:
- Correct spelling and grammar.
- Reframe unclear questions if necessary without changing meaning.
- For each MCQ:
    - Create options A, B, C, D.
    - Add an invented wrong option E (different from the correct answer).
    - Match the correct answer using the exact text of the correct option (not just A/B/C).
    - Add a short 1-2 sentence explanation_text for why the correct answer is correct.
    - Set difficulty as "easy".
    - Leave created_at blank.
Format the final output as a CSV text **only**, no extra notes, no formatting:
Columns must be:
id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at
Start id numbering from 1 upwards.
Do not output JSON or markdown, only raw CSV text.
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

st.title("🧠 MCQ Cleaner to CSV (with Explanations)")
st.write("Paste messy MCQs and answers, get a clean CSV instantly!")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300)

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys (e.g., 1.B 2.A 3.C)", height=100)

if st.button("🚀 Generate CSV"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        user_prompt = f"Here are the MCQs:\n{raw_mcqs}\n\nHere are the correct answers:\n{answer_keys}"
        with st.spinner("Talking to OpenAI..."):
            csv_text = call_openai(user_prompt)
        
        try:
            # Show and allow download
            st.success("✅ MCQs cleaned successfully!")
            st.download_button(
                label="📥 Download CSV",
                data=csv_text,
                file_name=f"mcqs_cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            # Also show preview table
            df = pd.read_csv(StringIO(csv_text))
            st.dataframe(df)

        except Exception as e:
            st.error(f"⚠️ Error parsing OpenAI response: {e}")
            st.code(csv_text)
