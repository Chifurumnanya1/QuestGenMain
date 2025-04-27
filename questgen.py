# app.py

import streamlit as st
import re
import openai

# 1. App configuration
st.set_page_config(
    page_title="MCQ Formatter AI Pipeline",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Sidebar / Secrets
# Streamlit Cloud stores your secret as OPENAI_API_KEY in st.secrets
openai.api_key = st.secrets["OPENAI_API_KEY"]

# 3. UI
st.title("MCQ Formatter AI Pipeline")
st.markdown(
    """
    Paste your block of MCQ questions and the corresponding answers below.
    The AI will:
    - Improve readability of each question
    - Generate a wrong 5th option (`option_e`)
    - Provide an explanation for the correct answer
    The output uses `===ENTRY===` delimiters so you can parse it into JSON locally.
    """
)

questions_block = st.text_area("MCQ Questions Block", height=300, help="Include numbered questions with options (a)-(d).")
answers_block = st.text_area("Answers Block", height=150, help="Format like `1C 2A 3D ...`")

if st.button("Format MCQs"):
    # 4. Parse questions
    lines = questions_block.splitlines()
    questions = []
    for line in lines:
        m = re.match(r'^\s*(\d+)\.\s*(.+)$', line)
        if m:
            questions.append(m.group(2).strip())
    
    # 5. Parse answers
    # Matches patterns like "1C" or "2. A"
    raw = answers_block.replace(",", " ")
    answer_pairs = re.findall(r'(\d+)\.?\s*([A-E])', raw, re.IGNORECASE)
    # Sort by question number
    answer_pairs.sort(key=lambda x: int(x[0]))
    answers = [ans.upper() for _, ans in answer_pairs]
    
    if len(questions) != len(answers):
        st.error(f"Parsed {len(questions)} questions but {len(answers)} answers. Please check formatting.")
    else:
        # 6. Build prompt
        q_block = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        a_block = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))
        prompt = f"""Here are the multiple choice questions:
{q_block}

Here are the corresponding correct answers:
{a_block}

For each question:
- Improve readability of the question text.
- Generate a completely wrong fifth option (option_e).
- Provide an explanation_text for the correct answer.

Output the results in plain text. For each question entry, use "===ENTRY===" as a delimiter before it, and inside each entry format exactly as:

QUESTION_TEXT: <improved question>
OPTION_E: <wrong option>
EXPLANATION_TEXT: <explanation>

Do not include any additional text."""
        
        # 7. Call OpenAI
        with st.spinner("Formatting MCQs, please wait..."):
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert at formatting MCQ questions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=outputs := None  # Let API decide; adjust if needed
            )
            formatted = resp.choices[0].message.content.strip()
        
        # 8. Display result
        st.subheader("Formatted MCQs (Delimited)")
        st.code(formatted, language="text")
