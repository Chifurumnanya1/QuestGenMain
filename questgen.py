import re
import json
import io
import streamlit as st


# ── Helper --------------------------------------------------------------------
def clean(text: str) -> str:
    """Trim ends and collapse internal whitespace."""
    return re.sub(r"\s+", " ", text.strip())


def parse_questions(txt: str) -> list[dict]:
    """Return a list of question-dicts in the required schema."""
    questions = []

    # split into Q-blocks → from “Q<number>.” up to next “Q<number>.” or EOF
    for block in re.findall(r"(Q\d+\.[\s\S]*?)(?=\nQ\d+\.|\Z)", txt, re.MULTILINE):
        q_line, rest = block.split("\n", maxsplit=1)
        question_text = clean(re.sub(r"^Q\d+\.\s*", "", q_line))

        # options
        opts = dict(re.findall(r"^\s*\(([A-D])\)\s*(.*)", rest, re.MULTILINE))
        option_a = clean(opts.get("A", ""))
        option_b = clean(opts.get("B", ""))
        option_c = clean(opts.get("C", ""))
        option_d = clean(opts.get("D", ""))

        # answer & explanation
        ans_m = re.search(r"^Answer:\s*(.*)", rest, re.MULTILINE)
        correct_answer = clean(ans_m.group(1)) if ans_m else ""

        expl_m = re.search(r"Explanation:\s*([\s\S]*?)(?:\n\s*\n|\Z)", rest)
        explanation_text = clean(expl_m.group(1)) if expl_m else ""

        questions.append(
            {
                "question_text": question_text,
                "option_a": option_a,
                "option_b": option_b,
                "option_c": option_c,
                "option_d": option_d,
                "correct_answer": correct_answer,
                "explanation_text": explanation_text,
                "difficulty": "easy",
                "created_at": "",
            }
        )
    return questions


# ── Streamlit UI --------------------------------------------------------------
st.title("TXT → JSON converter for ReadyRN-style questions")

uploaded = st.file_uploader("Upload your .txt file", type=["txt"])
if uploaded:
    raw_text = uploaded.read().decode("utf-8", errors="ignore")
    data = parse_questions(raw_text)

    st.success(f"Parsed **{len(data)}** questions.")
    if st.checkbox("Show first item"):
        st.json(data[0] if data else {})

    # prepare JSON for download
    json_bytes = io.BytesIO()
    json_bytes.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    json_bytes.seek(0)

    st.download_button(
        label="📥 Download JSON",
        data=json_bytes,
        file_name="questions.json",
        mime="application/json",
    )
else:
    st.info("➡️  Upload a ReadyRN questions text file to begin.")
