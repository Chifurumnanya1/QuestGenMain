# streamlit_app.py
# ──────────────────────────────────────────────────────────
"""
Workflow
1. Paste QUESTIONS and ANSWERS.
2. GPT-4o rewrites each question & five options, then emits
   the compact delimiter block:
       ##question
       **option_a
       **option_b
       **option_c
       **option_d
       **option_e
       %%difficulty
       &&explanation_text
3. App parses blocks → JSON (created_at="").
4. Both raw text & JSON offered for download.
"""

import json, re, textwrap
from datetime import datetime, timezone
import openai, streamlit as st

openai.api_key = st.secrets["openai_api_key"]

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
    • Produce FIVE options (A–E). If only 4 exist, invent E.
    • Fix grammar/punctuation throughout.
    • Choose the correct option using the answer key provided.
    • Output in *exactly* this delimiter format:

    ##<question text>
    **<option_a>
    **<option_b>
    **<option_c>
    **<option_d>
    **<option_e>
    %%<difficulty: easy|medium|hard>
    &&<≤80-word explanation explaining why correct is right & others wrong>

    ✱ Separate questions with ONE blank line.
    ✱ Do NOT output JSON, markdown, or anything else.
""")

# ──────────────────────────────────────────────────────────
# 2 · Regex helpers for local parsing
# ──────────────────────────────────────────────────────────
BLOCK_SPLIT = re.compile(r"\n\s*\n")           # blank line
OPT_RE      = re.compile(r"\*\*(.+)")
DIFF_RE     = re.compile(r"%%\s*(\w+)")
EXP_RE      = re.compile(r"&&\s*(.+)")
LETTER2FIELD= {"A":"option_a","B":"option_b","C":"option_c",
               "D":"option_d","E":"option_e"}

ANS_RE      = re.compile(r"(\d+)\s*\.\s*([A-Ea-e])")

def parse_block(block: str, correct_letter: str):
    lines = block.strip().splitlines()
    if not lines or not lines[0].startswith("##") or len(lines) < 8:
        raise ValueError("Malformed block")
    stem = lines[0][2:].strip()
    options = [OPT_RE.match(l).group(1).strip() for l in lines[1:6]]
    difficulty = DIFF_RE.match(lines[6]).group(1).lower()
    explanation = EXP_RE.match(lines[7]).group(1).strip()

    rec = {
        "question_text": stem,
        "option_a": options[0],
        "option_b": options[1],
        "option_c": options[2],
        "option_d": options[3],
        "option_e": options[4],
        "correct_answer": None,  # filled next
        "explanation_text": explanation,
        "difficulty": difficulty,
        "created_at": "",
    }
    if correct_letter and correct_letter.upper() in LETTER2FIELD:
        rec["correct_answer"] = rec[LETTER2FIELD[correct_letter.upper()]]
    return rec

# ──────────────────────────────────────────────────────────
# 3 · Streamlit UI
# ──────────────────────────────────────────────────────────
st.title("🧠 MCQ → JSON via Delimiter Blocks")

raw_q = st.text_area("QUESTIONS block", height=300)
raw_a = st.text_area("ANSWERS block (e.g. 1. C  2. A …)", height=120)

if st.button("Generate"):
    if not raw_q.strip() or not raw_a.strip():
        st.error("Both blocks are required.")
        st.stop()

    # build answer map
    ans_map = {int(n): l.upper() for n, l in ANS_RE.findall(raw_a)}

    # crude split by numbered header
    q_chunks = [q.strip() for q in
                re.split(r"\n(?=\d+\.)", raw_q.strip()) if q.strip()]

    all_blocks = []
    # ─── GPT in batches ───
    for i in range(0, len(q_chunks), QUESTIONS_PER_BATCH):
        batch = q_chunks[i:i+QUESTIONS_PER_BATCH]
        # add answer letter line to each chunk
        user_payload = []
        for chunk in batch:
            num_match = re.match(r"(\d+)", chunk)
            q_num = int(num_match.group(1)) if num_match else -1
            letter = ans_map.get(q_num, "")
            user_payload.append(f"{chunk}\n\nAnswer: {letter}")
        user_msg = "\n\n---\n\n".join(user_payload)

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

    # ─── local parse ───
    recs = []
    for blk_text in BLOCK_SPLIT.split(raw_output):
        # extract question number (first digits of stem, fallback incremental)
        num_match = re.match(r"##\s*(\d+)", blk_text)
        q_num = int(num_match.group(1)) if num_match else len(recs)+1
        recs.append(parse_block(blk_text, ans_map.get(q_num, "")))

    # ─── downloads ───
    raw_bytes  = raw_output.encode("utf-8")
    json_bytes = json.dumps(recs, indent=2, ensure_ascii=False).encode()

    st.download_button("📥 raw_gpt_output.txt", raw_bytes,
                       "raw_gpt_output.txt", "text/plain")
    st.download_button("📥 mcq_output.json", json_bytes,
                       "mcq_output.json", "application/json")

    st.success(f"{len(recs)} questions processed!")
    st.code(json.dumps(recs[:2], indent=2, ensure_ascii=False) + "\n…",
            language="json")
