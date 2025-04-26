import streamlit as st
import openai
import pandas as pd
from io import StringIO
from datetime import datetime
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# System prompt (new!)
SYSTEM_PROMPT = """
You are an expert MCQ formatter.
You will receive messy MCQs and answer keys.
Your tasks are:
- Correct spelling and grammar.
- Reframe unclear questions without changing meaning.
- Present each MCQ as:
    - question_text
    - options A, B, C, D
    - invent a wrong Option E (different from the correct answer)
    - correct_answer should be the EXACT text of the correct option
    - generate a short 1-2 sentence explanation for the correct answer
- Assume difficulty is "easy" unless stated otherwise.
- created_at field should be blank.
Format everything in this JSON structure:
[
 {
   "question_text": "...",
   "difficulty": "easy",
   "correct_answer": "...",
   "option_a": "...",
   "option_b": "...",
   "option_c": "...",
   "option_d": "...",
   "option_e": "...",
   "explanation_text": "...",
   "created_at": ""
 },
 {... next question }
]
ONLY output valid JSON array, no text around it.
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

st.title("🧠 MCQ Cleaner + CSV Generator with Explanations")
st.write("Paste your messy MCQs and answers, get a ready-to-use CSV for your database!")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300)

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys (e.g., 1.B 2.A 3.C)", height=100)

if st.button("🚀 Clean, Generate Explanations & Create CSV"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        user_prompt = f"Here are the MCQs:\n{raw_mcqs}\n\nHere are the correct answers:\n{answer_keys}"
        with st.spinner("Talking to OpenAI..."):
            cleaned_json = call_openai(user_prompt)
        
        try:
            # Parse the JSON
            mcq_data = pd.read_json(StringIO(cleaned_json))
            mcq_data.insert(0, 'id', range(1, len(mcq_data) + 1))  # Add ID column
            
            st.success("✅ MCQs generated successfully! Download your CSV below.")
            
            csv = mcq_data.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"cleaned_mcqs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
            
            st.dataframe(mcq_data)  # Show the table in the app

        except Exception as e:
            st.error(f"⚠️ Error processing OpenAI response: {e}")
            st.code(cleaned_json)
