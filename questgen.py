import streamlit as st
from openai import OpenAI
import pandas as pd
from datetime import datetime
from io import StringIO, BytesIO

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# SYSTEM PROMPT (strict CSV rules)
SYSTEM_PROMPT = """
You are an expert MCQ formatter and CSV generator.
You will receive messy MCQs and answer keys.

For each MCQ:
- Correct grammar and structure.
- Create four options: A, B, C, D.
- Invent an extra wrong option E.
- Match correct_answer by full exact option text.
- Generate a short 1-2 line explanation_text.
- Set difficulty as "easy".
- Leave created_at blank.

Format ONLY clean CSV with this header:

id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at

STRICT RULES:
- Enclose every text field inside double quotes ("...") if necessary.
- Escape any internal quotes properly.
- Ensure clean CSV format, no markdown, no JSON, no extra text.
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

def split_into_batches(text_list, batch_size=30):
    for i in range(0, len(text_list), batch_size):
        yield text_list[i:i+batch_size]

# Streamlit App
st.set_page_config(page_title="MCQ Excel Generator", page_icon="📄", layout="wide")
st.title("📄 MCQ Cleaner and Excel Generator (with Batching & Download)")
st.write("Paste your messy MCQs and answers. AI will clean, explain, and give you an Excel file!")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300, placeholder="Paste your questions and options here...")

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys", height=100, placeholder="Example: 1.B 2.A 3.C")

if st.button("🚀 Generate Excel File"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        mcq_lines = raw_mcqs.strip().split("\n")
        batches = list(split_into_batches(mcq_lines, batch_size=30))
        
        all_batches = []
        current_id = 1
        
        for batch_num, batch in enumerate(batches):
            batch_text = "\n".join(batch)
            user_prompt = f"Here are some MCQs:\n{batch_text}\n\nHere are the correct answers:\n{answer_keys}"
            with st.spinner(f"Processing batch {batch_num + 1} of {len(batches)}..."):
                batch_csv = call_openai(user_prompt)

            # Parse batch CSV safely
            batch_csv_io = StringIO(batch_csv)
            df_batch = pd.read_csv(batch_csv_io, quoting=1)

            df_batch['id'] = range(current_id, current_id + len(df_batch))
            current_id += len(df_batch)

            all_batches.append(df_batch)

        # Combine all batches into a single DataFrame
        final_df = pd.concat(all_batches, ignore_index=True)

        # Generate Excel file in memory
        excel_buffer = BytesIO()
        final_df.to_excel(excel_buffer, index=False, sheet_name="MCQs")
        excel_buffer.seek(0)

        st.success("✅ MCQs cleaned and formatted successfully!")

        # Download button
        st.download_button(
            label="📥 Download MCQs as Excel File (.xlsx)",
            data=excel_buffer,
            file_name=f"mcqs_cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.subheader("🔎 Preview of Cleaned MCQs:")
        st.dataframe(final_df)
