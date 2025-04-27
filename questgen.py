import streamlit as st
from openai import OpenAI
import pandas as pd
from datetime import datetime
from io import StringIO, BytesIO

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# SYSTEM PROMPT
SYSTEM_PROMPT = """
You are an expert MCQ formatter and CSV generator.
You will receive messy MCQs and answer keys.

For each MCQ:
- Correct grammar and structure.
- Create options A, B, C, D.
- Invent a wrong option E.
- Match correct_answer using the exact text from the correct option.
- Generate a short explanation_text.
- Set difficulty as "easy".
- Leave created_at blank.

Format ONLY clean CSV text with this header:

id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at

STRICT RULES:
- Enclose every text field inside double quotes ("...") if necessary.
- Escape internal quotes properly.
- No markdown, no JSON, no extra text.
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

def split_into_batches(lst, batch_size=30):
    for i in range(0, len(lst), batch_size):
        yield lst[i:i+batch_size]

def parse_answer_keys(answer_text):
    # Parse "1.B 2.A 3.C" into a dictionary
    mapping = {}
    parts = answer_text.strip().split()
    for p in parts:
        if '.' in p:
            q_num, ans = p.split('.')
            mapping[int(q_num.strip())] = ans.strip().upper()
    return mapping

# Streamlit App
st.set_page_config(page_title="MCQ Excel Generator", page_icon="📄", layout="wide")
st.title("📄 MCQ Cleaner and Excel Generator (Safe Batching)")

st.subheader("📝 Paste Your Raw MCQs Below")
raw_mcqs = st.text_area("Raw MCQs", height=300, placeholder="Paste your MCQ questions here...")

st.subheader("🔑 Paste Your Answer Keys Below")
answer_keys = st.text_area("Answer Keys", height=100, placeholder="Example: 1.B 2.A 3.C 4.D")

if st.button("🚀 Generate Excel File"):
    if not raw_mcqs.strip() or not answer_keys.strip():
        st.error("⚠️ Please paste both MCQs and Answer Keys.")
    else:
        mcq_lines = raw_mcqs.strip().split("\n")
        answers_dict = parse_answer_keys(answer_keys)

        batches = list(split_into_batches(mcq_lines, batch_size=30))
        all_batches = []
        current_id = 1
        
        for batch_num, batch_mcqs in enumerate(batches):
            batch_start = batch_num * 30 + 1
            batch_end = batch_start + len(batch_mcqs) - 1
            
            # Prepare matching answers for this batch
            batch_answers = " ".join(
                f"{q}.{answers_dict[q]}" for q in range(batch_start, batch_end + 1) if q in answers_dict
            )
            
            batch_text = "\n".join(batch_mcqs)
            user_prompt = f"Here are some MCQs:\n{batch_text}\n\nHere are the correct answers:\n{batch_answers}"
            
            with st.spinner(f"Processing batch {batch_num + 1} of {len(batches)}..."):
                batch_csv = call_openai(user_prompt)

            batch_csv_cleaned = "\n".join([line for line in batch_csv.splitlines() if line.strip()])

            batch_csv_io = StringIO(batch_csv_cleaned)
            df_batch = pd.read_csv(batch_csv_io, quoting=1)

            # Fix ID numbering
            df_batch['id'] = range(current_id, current_id + len(df_batch))
            current_id += len(df_batch)

            all_batches.append(df_batch)

        final_df = pd.concat(all_batches, ignore_index=True)

        # Create Excel file
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            final_df.to_excel(writer, index=False, sheet_name="MCQs")

        excel_buffer.seek(0)

        st.success("✅ MCQs generated successfully!")

        st.download_button(
            label="📥 Download MCQs (Excel .xlsx)",
            data=excel_buffer,
            file_name=f"mcqs_cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.subheader("🔎 Preview of MCQs:")
        st.dataframe(final_df)
