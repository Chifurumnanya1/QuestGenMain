# streamlit_app.py
# ──────────────────────────────────────────────────────────
"""
MCQ Cleaner  →  Delimiter Blocks  →  JSON  (Auto-batch & robust)

• Paste *QUESTIONS* block (any messy layout)
• Paste *ANSWERS*  block (“1. C  2. A …”)

Flow
1. Compute safe batch size so GPT-4o output never truncates.
2. GPT rewrites each question, adds option E (if missing),
   fixes grammar, then outputs delimiter blocks:
       ##question
       **option_a
       **option_b
       **option_c
       **option_d
       **option_e
       %%difficulty
       &&explanation_text
3. Local Python parses blocks → JSON, inserts created_at = "".
4. Downloads:
   • gpt_blocks.txt   – raw delimiter output
   • mcq_output.json  – ready for Supabase
"""

import json, re, textwrap
from datetime import datetime, timezone
from typing import Optional

import openai, streamlit as st

# ─────────── CONFIG ───────────
openai.api_key = st.secrets["openai_api_key"]
MODEL              = "gpt-4o"
TEMPERATURE        = 0.15
MAX_MODEL_TOKENS   = 8000                       # GPT-4o hard limit
TOKENS_PER_MCQ     = 180                       # empirical worst-case
TOKENS_PROMPT_HEAD = 750                       # system + other text
# ───────────────────────────────

def best_batch_size(total_q: int) -> int:
    usable = MAX_MODEL_TOKENS - TOKENS_PROMPT_HEAD
    return max(1, min(10, usable // TOKENS_PER_MCQ))

# ───────── SYSTEM PROMPT ─────────
SYSTEM_MSG = textwrap.dedent("""
    You are an expert medical-education content formatter.
    For EACH incoming MCQ:
      1. Rewrite the stem clearly.
      2. Provide FIVE options (A–E).  If source has only four, invent E (must be wrong).
      3. Use the supplied answer letter to know which option is correct.
      4. Write ≤80-word explanation of why that option is correct / others wrong.
      5. Label difficulty: easy | medium | hard.
    OUTPUT ONLY in this delimiter format:

    ##<stem>
    **<option_a>
    **<option_b>
    **<option_c>
    **<option_d>
    **<option_e>
    %%<difficulty>
    &&<explanation_text>

    Separate MCQs with ONE blank line.  No JSON, markdown, or commentary.
""")

# ───────── REGEX HELPERS ─────────
BLOCK_SPLIT  = re.compile(r"\n\s*\n")
OPT_RE       = re.compile(r"\*\*(.+)")
DIFF_RE      = re.compile(r"%%\s*(\w+)")
EXP_RE       = re.compile(r"&&\s*(.+)")
ANS_RE       = re.compile(r"(\d+)\s*\.\s*([A-Ea-e])")

LETTER2FIELD = {"A":"option_a","B":"option_b",
                "C":"option_c","D":"option_d","E":"option_e"}

def safe(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.match(text)
    return m.group(1).strip() if m else None

def parse_block(block: str, correct_letter: str) -> dict:
    lines = [ln for ln in block.strip().splitlines() if ln.strip()]
    if len(lines) < 7 or not lines[0].startswith("##"):
        raise ValueError("bad block")

    stem = lines[0][2:].strip()
    opts = [safe(OPT_RE, l) or "" for l in lines[1:6]]
    while len(opts) < 5:
        opts.append("")

    diff  = safe(DIFF_RE, lines[6]) or "medium"
    expl  = safe(EXP_RE,  lines[7]) if len(lines) > 7 else ""

    rec = {
        "question_text": stem,
        "option_a": opts[0],
        "option_b": opts[1],
        "option_c": opts[2],
        "option_d": opts[3],
        "option_e": opts[4],
        "correct_answer": None,
        "explanation_text": expl,
        "difficulty": diff.lower(),
        "created_at": "",
    }
    fld = LETTER2FIELD.get(correct_letter.upper(), "")
    if fld and rec[fld]:
        rec["correct_answer"] = rec[fld]
    else:
        rec["explanation_text"] += "  (Answer key mismatch – please review.)"
    return rec

# ───────── STREAMLIT UI ─────────
st.title("🧠 MCQ → Delimiter → JSON  (Auto-batch)")

raw_q = st.text_area("QUESTIONS block", height=300)
raw_a = st.text_area("ANSWERS block (e.g. 1. C  2. A …)", height=120)

if st.button("Generate"):
    if not raw_q.strip() or not raw_a.strip():
        st.error("Both blocks required.")
        st.stop()

    ans_map = {int(n): l.upper() for n, l in ANS_RE.findall(raw_a)}
    q_chunks = [c.strip() for c in re.split(r"\n(?=\d+\.)", raw_q.strip()) if c.strip()]

    QUESTIONS_PER_BATCH = best_batch_size(len(q_chunks))
    st.info(f"GPT batch size = {QUESTIONS_PER_BATCH}")

    all_blocks = []
    for i in range(0, len(q_chunks), QUESTIONS_PER_BATCH):
        batch = q_chunks[i:i+QUESTIONS_PER_BATCH]
        payloads = []
        for chunk in batch:
            m = re.match(r"(\d+)", chunk)
            q_num = int(m.group(1)) if m else 10000 + len(payloads)
            letter = ans_map.get(q_num, "")
            payloads.append(f"{chunk}\n\nAnswer: {letter}")

        rsp = openai.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            messages=[{"role":"system","content":SYSTEM_MSG},
                      {"role":"user",  "content":"\n\n---\n\n".join(payloads)}],
        ).choices[0].message.content.strip()
        all_blocks.append(rsp)

    gpt_text = "\n\n".join(all_blocks)

    # local parse
    records = []
    for blk in BLOCK_SPLIT.split(gpt_text):
        num_match = re.match(r"##\s*(\d+)", blk)
        q_num = int(num_match.group(1)) if num_match else None
        try:
            records.append(parse_block(blk, ans_map.get(q_num, "")))
        except ValueError:
            st.warning("Skipped malformed block.")

    # downloads
    st.download_button("📥 gpt_blocks.txt",
                       gpt_text.encode(), "gpt_blocks.txt", "text/plain")
    st.download_button("📥 mcq_output.json",
                       json.dumps(records, indent=2, ensure_ascii=False).encode(),
                       "mcq_output.json", "application/json")

    st.success(f"{len(records)} questions processed!")
    st.code(json.dumps(records[:2], indent=2, ensure_ascii=False) + "\n…",
            language="json")
