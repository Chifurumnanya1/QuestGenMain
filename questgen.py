import streamlit as st
from openai import OpenAI
import pandas as pd
from datetime import datetime
from io import StringIO, BytesIO
import textwrap, re, time

# --------------------  CONFIG  --------------------
st.set_page_config(page_title="MCQ → Excel (self-healing)",
                   page_icon="📄", layout="wide")

# OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = """
You are an expert MCQ formatter and CSV generator.
For each MCQ you receive you must:
- Correct grammar.
- Provide 5 options: A,B,C,D (real) plus E (wrong filler).
- Use the full option text for correct_answer.
- Add a 1–2-sentence explanation_text.
- difficulty = "easy", created_at = blank.
Return **ONLY** pure CSV rows with this header:
id,question_text,difficulty,correct_answer,option_a,option_b,option_c,option_d,option_e,explanation_text,created_at
Wrap any field that contains a comma or quote in double quotes, escape internal quotes (“text → ""text"").
Never leave blank lines between rows.
Never output markdown, JSON or commentary.
"""

# --------------------  HELPERS  --------------------
def chat(prompt: str) -> str:
    """Call GPT-4o and return assistant content."""
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt}
        ],
        temperature=0.15,
        max_tokens=4000)
    return resp.choices[0].message.content

def parse_answers(raw: str) -> dict[int,str]:
    """'1.B 2.A 3.C'  →  {1:'B',2:'A',3:'C'}"""
    out = {}
    for piece in re.findall(r'(\d+\.[A-Ea-e])', raw):
        q, ans = piece.split('.')
        out[int(q)] = ans.upper()
    return out

def split_batches(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n], i            # i == index offset (0-based)

def rows_ok(df: pd.DataFrame, expected: int) -> bool:
    return len(df) == expected and not df.isna().all(axis=1).any()

# --------------------  UI  --------------------
st.title("📄 MCQ Cleaner → Excel (with auto-retry)")

batch_size_ui = st.sidebar.selectbox(
    "Initial batch size", [10, 20, 30, 40, 50], index=2)

raw_mcqs   = st.text_area("Paste raw MCQs", height=300)
raw_keys   = st.text_area("Paste answer keys (e.g. 1.B 2.A …)", height=100)
retry_log  = st.sidebar.empty()

if st.button("🚀 Generate Excel"):
    if not raw_mcqs.strip() or not raw_keys.strip():
        st.warning("Please provide both MCQs and answer keys.")
        st.stop()

    mcq_blocks = [blk.strip() for blk in re.split(r'\n(?=\d+\.)', raw_mcqs) if blk.strip()]
    answers    = parse_answers(raw_keys)

    bad_chunks = []
    dfs        = []
    next_id    = 1

    for chunk, offset in split_batches(mcq_blocks, batch_size_ui):
        start_no = offset+1
        end_no   = offset+len(chunk)
        key_subset = " ".join(f"{n}.{answers.get(n,'')}" for n in range(start_no, end_no+1) if n in answers)

        prompt = f"MCQs:\n{'\n'.join(chunk)}\n\nAnswers:\n{key_subset}"
        with st.spinner(f"Batch {start_no}–{end_no}"):
            csv_text = chat(prompt)

        cleaned = "\n".join(x for x in csv_text.splitlines() if x.strip())
        df = pd.read_csv(StringIO(cleaned), quoting=1)

        if not rows_ok(df, len(chunk)):                # first try failed ➜ retry by 10s
            retry_log.warning(f"❗ Retry batch {start_no}-{end_no} in sub-chunks of 10")
            for sub, sub_off in split_batches(chunk, 10):
                s_start = start_no + sub_off
                s_end   = s_start + len(sub)-1
                sub_ans = " ".join(f"{n}.{answers.get(n,'')}" for n in range(s_start, s_end+1) if n in answers)
                sub_prompt = f"MCQs:\n{'\n'.join(sub)}\n\nAnswers:\n{sub_ans}"
                with st.spinner(f"Retry {s_start}–{s_end}"):
                    sub_csv = chat(sub_prompt)
                sub_df = pd.read_csv(StringIO("\n".join(l for l in sub_csv.splitlines() if l.strip())), quoting=1)

                if rows_ok(sub_df, len(sub)):
                    df = pd.concat([df, sub_df], ignore_index=True)
                else:
                    bad_chunks.extend(range(s_start, s_end+1))

        # re-index IDs
        df["id"] = range(next_id, next_id+len(df))
        next_id += len(df)
        dfs.append(df)

    final_df = pd.concat(dfs, ignore_index=True)

    if bad_chunks:
        retry_log.error(f"⚠️ Still missing rows for: {bad_chunks}")

    # ---------------- Excel output ----------------
    xls = BytesIO()
    with pd.ExcelWriter(xls, engine="openpyxl") as wrt:
        final_df.to_excel(wrt, index=False, sheet_name="MCQs")
    xls.seek(0)

    st.success(f"Done! {len(final_df)} MCQs processed.")
    st.download_button("📥 Download Excel",
                       data=xls,
                       file_name=f"mcqs_{datetime.utcnow():%Y%m%d_%H%M%S}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.subheader("Preview")
    st.dataframe(final_df, use_container_width=True)
