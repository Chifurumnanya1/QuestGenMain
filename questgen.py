import streamlit as st
from openai import OpenAI
import io

# Page Configuration
st.set_page_config(
    page_title="MCQ to CSV via OpenAI",
    page_icon="🤖",
    layout="wide"
)

# Build the system prompt

def build_prompt(questions: str, answers: str) -> str:
    return f"""
You are an expert assistant that transforms every provided multiple-choice question into a CSV file—do not output only a sample.

Input:
- All questions with options A-D in a text block.
- Answers listing question numbers and letters (e.g., 1.A 2.C ...).

Tasks:
1. Parse all questions and their options (do not omit any).
2. Map each correct answer letter to its full option text.
3. Generate a plausible wrong option E for each question.
4. Write a concise explanation for why the chosen answer is correct.
5. Assign difficulty="easy" if factual, else "medium".
6. Use topic_id=3 and created_at="2025-04-26 00:00:00".
7. Output ONLY the raw CSV content with header, without any preamble or postamble:
   id,topic_id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at

Ensure all fields are comma-separated and quote fields containing commas.

---
{questions}\n\n{answers}
"""  # noqa

# Cached call to OpenAI
@st.cache_data

def generate_csv_from_openai(prompt: str, api_key: str) -> str:
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=4096
    )
    return response.choices[0].message.content.strip()

# Sidebar Configuration
st.sidebar.header("Configuration")
api_key = st.sidebar.text_input(
    "OpenAI API Key", 
    value=st.secrets.get("OPENAI_API_KEY", ""),
    type="password",
    help="Store in Streamlit Cloud secrets as OPENAI_API_KEY."
)

# Main UI
st.title("🤖 MCQ to CSV Generator")
st.markdown("Paste your questions and answers, then click **Generate CSV**.")

questions_text = st.text_area(
    "Questions + Options (A-D)",
    height=300,
    placeholder="1. Sample question? a. Opt1 b. Opt2 c. Opt3 d. Opt4"
)

answers_text = st.text_area(
    "Answer Key (e.g., 1.B 2.A 3.C)",
    height=100,
    placeholder="1.B 2.A 3.C ..."
)

if st.button("Generate CSV"):
    if not api_key:
        st.error("🔑 Enter your OpenAI API key in the sidebar.")
    elif not questions_text.strip() or not answers_text.strip():
        st.error("✏️ Paste both questions and answers.")
    else:
        prompt = build_prompt(questions_text, answers_text)
        with st.spinner("⏳ Generating CSV via OpenAI..."):
            try:
                csv_output = generate_csv_from_openai(prompt, api_key)
                st.success("✅ CSV generated!")
                st.download_button(
                    "📥 Download CSV",
                    data=csv_output,
                    file_name="mcq_questions.csv",
                    mime="text/csv"
                )
            except Exception as e:
                st.error(f"❌ {e}")

# Footer
st.markdown("---")
st.caption("Built with ❤️ using Streamlit & OpenAI v1 API")
