import streamlit as st
import openai
import io

# Page configuration
st.set_page_config(
    page_title="MCQ to CSV via OpenAI",
    page_icon="🤖",
    layout="wide"
)

# Helper functions
def build_prompt(questions: str, answers: str) -> str:
    return f"""
You are an expert assistant that transforms multiple-choice questions into a CSV file.

Input:
- Questions with options A-D in a text block.
- Answers listing question numbers and letters (e.g., 1.A 2.C ...).

Tasks:
1. Parse questions and their options.
2. Map the correct answer letters to the full option text.
3. Generate a plausible wrong option E for each question.
4. Write a concise explanation for the correct answer.
5. Assign `difficulty` = "easy" if direct factual, else "medium".
6. Use `topic_id` = 3 and `created_at` = "2025-04-26 00:00:00".
7. Output CSV text with header:
   id,topic_id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at

Ensure proper CSV quoting for commas inside fields.

---
{questions}\n\n{answers}
"""  # noqa

@st.cache_data
def generate_csv_from_openai(prompt: str, api_key: str) -> str:
    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=4096
    )
    return response.choices[0].message.content.strip()

# Sidebar for inputs
st.sidebar.header("Configuration")
api_key_input = st.sidebar.text_input(
    "OpenAI API Key",
    value=st.secrets.get("OPENAI_API_KEY", ""),
    type="password",
    help="Store your key in Streamlit Cloud secrets as OPENAI_API_KEY for security."
)

st.sidebar.markdown("---")
difficulty_hint = st.sidebar.selectbox(
    "Default difficulty threshold",
    options=["20 questions → easy; else medium", "All easy", "All medium"],
    index=0,
    help="Choose how difficulty is assigned."
)

# Main UI
st.title("🤖 MCQ to CSV Generator")
st.markdown(
    "Paste your questions and answer key, then click **Generate CSV**."
)
questions_text = st.text_area(
    "Questions + Options (A-D)",
    height=300,
    placeholder="1. Question text? a. Option1 b. Option2 c. Option3 d. Option4"
)
answers_text = st.text_area(
    "Answer Key (e.g., 1.B 2.A 3.C)",
    height=100,
    placeholder="1.B 2.A 3.C ..."
)

if st.button("Generate CSV"):
    if not api_key_input:
        st.error("🔑 Please provide your OpenAI API key in the sidebar.")
    elif not questions_text.strip() or not answers_text.strip():
        st.error("✏️ Please paste both the questions and the answers.")
    else:
        prompt = build_prompt(questions_text, answers_text)
        with st.spinner("⏳ Generating CSV via OpenAI..."):
            try:
                csv_output = generate_csv_from_openai(prompt, api_key_input)
                st.success("✅ CSV generated successfully.")
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_output,
                    file_name="mcq_questions.csv",
                    mime="text/csv"
                )
                st.text_area("CSV Preview", csv_output, height=300)
            except Exception as e:
                st.error(f"❌ Error: {e}")

# Footer
st.markdown("---")
st.caption("Built with ❤️ using Streamlit and OpenAI API")
