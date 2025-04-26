# streamlit_app.py
# ──────────────────────────────────────────────────────────
"""
MCQ → JSON via delimiter blocks  (robust version)

1. Paste QUESTIONS and ANSWERS.
2. GPT-4o rewrites each item and returns blocks like:

   ##question
   **option_a
   **option_b
   **option_c
   **option_d
   **option_e
   %%difficulty
   &&explanation_text

3. App parses those blocks locally → JSON (created_at = "").
4. Download both raw text and parsed JSON.
"""

import json, re, textwrap
from datetime import datetime, timezone
from typing import Optional

import openai, streamlit as st

openai.api_key = st.secrets["OPENAI_API_KEY"]

MODEL               = "gpt-4o"
QUESTIONS_PER_BATCH = 10
TEMPERATURE         = 0.2

# ──────────────────────────────────────────────────────────
# 1 · GPT prompt (no JSON in response!)
# ──────────────────────────────────────────────────────────
SYSTEM_MSG = textwrap.dedent("""
    You are an expert medical-education content formatter.
    For EVERY question you receive:
    • Rewrite the stem in clear English.
    • Provide FIVE options (A–E).  If only 4 exist, invent E (must be wrong).
    • Fix grammar & punctuation.
    • Use the supplied answer letter to know which option is correct.
    • Output ONLY in this delimiter format:

    ##<question text>
    **<option_a>
    **<option_b>
    **<option_c>
    **<option_d>
    **<option_e>
    %%<difficulty: easy|medium|hard>
    &&<≤80-word explanation>

    Separate MCQs with ONE blank line.  No JSON, markdown, or extra commentary.
""")

# ──────────────────────────────────────────────────────────
# 2 · Regex helpers
# ──────────────────────────────────────────────────────────
BLOCK_SPLIT  = re.compile(r"\n\s*\n")           # blank line splits blocks
OPT_RE       = re.compile(r"\*\*(.+)")
DIFF_RE      = re.compile(r"%%\s*(\w+)")
EXP_RE       = re.compile(r"&&\s*(.+)")

LETTER2FIELD = {"A": "option_a", "B": "option_b",
                "C": "option_c", "D": "option_d", "E": "option_e"}

ANS_RE       = re.compile(r"(\d+)\s*\.\s*([A-Ea-e])")

def safe_match(pattern: re.Pattern, text: str) -> Optional[str]:
    """Return first capture group or None."""
    m = pattern.match(text)
    return m.group(1).strip() if m else None


def parse_block(block: str, correct_letter: str) -> dict:
    """
    Convert one delimiter block to the final JSON object.
    Tolerates missing difficulty/explanation lines.
    """
    lines = [ln for ln in block.strip().splitlines() if ln.strip()]

    if len(lines) < 7 or not lines[0].startswith("##") or not lines[1].startswith("**"):
        raise ValueError("Malformed block")

    stem = lines[0][2:].strip()

    # First five option lines
    options = [safe_match(OPT_RE, ln) or "" for ln in lines[1:6]]
    while len(options) < 5:
        options.append("")

    difficulty  = safe_match(DIFF_RE, lines[6]) or "medium"
    explanation = safe_match(EXP_RE,  lines[7]) if len(lines) > 7 else ""

    rec = {
        "question_text": stem,
        "option_a": options[0],
        "option_b": options[1],
        "option_c": options[2],
        "option_d": options[3],
        "option_e": options[4],
        "correct_answer": None,
        "explanation_text": explanation,
        "difficulty": difficulty.lower(),
        "created_at": "",
    }
    if correct_letter and correct_letter.upper() in LETTER2FIELD:
        rec["correct_answer"] = rec[LETTER2FIELD[correct_letter.upper()]]
    return rec

# ──────────────────────────────────────────────────────────
# 3 · Streamlit UI
# ──────────────────────────────────────────────────────────
st.title("🧠 MCQ → JSON (delimiter pipeline, robust)")

raw_q = st.text_area("QUESTIONS block", height=300)
raw_a = st.text_area("ANSWERS block (e.g. 1. C  2. A …)", height=120)

if st.button("Generate"):
    if not raw_q.strip() or not raw_a.strip():
        st.error("Both QUESTIONS and ANSWERS are required.")
        st.stop()

    # answer map
    ans_map = {int(n): l.upper() for n, l in ANS_RE.findall(raw_a)}

    # split into rough chunks by "digit-dot"
    q_chunks = [q.strip() for q in
                re.split(r"\n(?=\d+\.)", raw_q.strip()) if q.strip()]

    all_blocks = []

    for i in range(0, len(q_chunks), QUESTIONS_PER_BATCH):
        batch = q_chunks[i:i+QUESTIONS_PER_BATCH]
        payloads = []
        for chunk in batch:
            # try to capture question number; fallback synthetic if missing
            m_num = re.match(r"(\d+)", chunk)
            if m_num:
                q_num = int(m_num.group(1))
            else:
                q_num = 10_000 + len(payloads)  # synthetic unlikely to clash
            letter = ans_map.get(q_num, "")
            payloads.append(f"{chunk}\n\nAnswer: {letter}")

        user_msg = "\n\n---\n\n".join(payloads)

        rsp = openai.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user",   "content": user_msg},
            ],
        ).choices[0].message.content.strip()

        all_blocks.append(rsp)

    raw_output = "\n\n".join(all_blocks)

    # parse each block locally
    records = []
    for blk in BLOCK_SPLIT.split(raw_output):
        num_match = re.match(r"##\s*(\d+)", blk)
        q_num = int(num_match.group(1)) if num_match else None
        try:
            rec = parse_block(blk, ans_map.get(q_num, ""))
            records.append(rec)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Skipped block due to parse error: {e}")

    # downloads
    raw_bytes  = raw_output.encode("utf-8")
    json_bytes = json.dumps(records, indent=2, ensure_ascii=False).encode()

    st.download_button("📥 raw_gpt_output.txt",
                       raw_bytes, file_name="raw_gpt_output.txt",
                       mime="text/plain")
    st.download_button("📥 mcq_output.json",
                       json_bytes, file_name="mcq_output.json",
                       mime="application/json")

    st.success(f"{len(records)} questions processed!")
    st.code(json.dumps(records[:2], indent=2, ensure_ascii=False) + "\n…",
            language="json")
