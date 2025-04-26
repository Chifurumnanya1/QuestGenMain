# streamlit_app.py
# ──────────────────────────────────────────────────────────
"""
MCQ Cleaner → Delimiter Blocks → JSON
• Auto-sizes GPT batches
• Keeps correct_answer in sync
• Adds newline before every «digit.» so ALL questions are detected
"""

import json, re, textwrap
from typing import Optional
import openai, streamlit as st

# ───────── CONFIG ─────────
openai.api_key       = st.secrets["OPENAI_API_KEY"]
MODEL                = "gpt-4o"
TEMPERATURE          = 0.15
MAX_MODEL_TOKENS     = 8000
TOKENS_PER_MCQ       = 180
TOKENS_PROMPT_HEAD   = 750
# ──────────────────────────
def best_batch_size(total_q: int) -> int:
    usable = MAX_MODEL_TOKENS - TOKENS_PROMPT_HEAD
    return max(1, min(10, usable // TOKENS_PER_MCQ))

# ───────── SYSTEM PROMPT ─────────
SYSTEM_MSG = textwrap.dedent("""
    You are an expert medical-education content formatter.
    For EACH MCQ you receive:
      • Rewrite stem clearly.
      • Provide FIVE options (A–E). If only four exist, invent E (wrong).
      • Use supplied answer letter to pick the correct option.
      • Write ≤80-word explanation why that option is correct.
      • Label difficulty: easy | medium | hard.
    Output ONLY in this delimiter format (blank line between questions):

    ##<stem>
    **<option_a>
    **<option_b>
    **<option_c>
    **<option_d>
    **<option_e>
    %%<difficulty>
    &&<explanation_text>
""")

# ───────── REGEX HELPERS ─────────
BLOCK_SPLIT = re.compile(r"\n\s*\n")
OPT_RE      = re.compile(r"\*\*(.+)")
DIFF_RE     = re.compile(r"%%\s*(\w+)")
EXP_RE      = re.compile(r"&&\s*(.+)")
ANS_RE      = re.compile(r"(\d+)\s*\.\s*([A-Ea-e])")
LETTER2FIELD= {"A":"option_a","B":"option_b","C":"option_c",
               "D":"option_d","E":"option_e"}

def safe(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.match(text)
    return m.group(1).strip() if m else None

def parse_block(block: str, letter: str) -> dict:
    lines = [ln for ln in block.strip().splitlines() if ln.strip()]
    if len(lines) < 7 or not lines[0].startswith("##"):
        raise ValueError("bad block")

    stem = lines[0][2:].strip()
    opts = [safe(OPT_RE, ln) or "" for ln in lines[1:6]]
    while len(opts) < 5:
        opts.append("")
    diff = safe(DIFF_RE, lines[6]) or "medium"
    expl = safe(EXP_RE,  lines[7]) if len(lines) > 7 else ""

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
    fld = LETTER2FIELD.get(letter.upper(), "")
    if fld and rec[fld]:
        rec["correct_answer"] = rec[fld]
    else:
        rec["explanation_text"] += " (Answer key mismatch – please review.)"
    return rec

# ───────── STREAMLIT UI ─────────
st.title("🧠 MCQ → Delimiter → JSON  (all questions detected)")

raw_q = st.text_area("QUESTIONS block", height=300)
raw_a = st.text_area("ANSWERS block (e.g. 1. C  2. A …)", height=120)

if st.button("Generate"):
    if not raw_q.strip() or not raw_a.strip():
        st.error("Both blocks required.")
        st.stop()

    ans_map = {int(n): l.upper() for n, l in ANS_RE.findall(raw_a)}

    # ---- NEW: force newline before every “digit.” pattern ----
    normalized = re.sub(r"\s*(\d+\.)", r"\n\1", raw_q.strip())
    q_chunks   = [c.strip() for c in re.split(r"\n(?=\d+\.)", normalized) if c.strip()]

    batch_sz = best_batch_size(len(q_chunks))
    st.info(f"GPT batch size = {batch_sz}")

    records   = []
    raw_parts = []

    for i in range(0, len(q_chunks), batch_sz):
        batch = q_chunks[i:i+batch_sz]
        letters, payloads = [], []

        for chunk in batch:
            m = re.match(r"(\d+)", chunk)
            q_num = int(m.group(1)) if m else 10000+len(letters)
            letter = ans_map.get(q_num, "")
            letters.append(letter)
            payloads.append(f"{chunk}\n\nAnswer: {letter}")

        gpt_reply = openai.chat.completions.create(
            model=MODEL, temperature=TEMPERATURE,
            messages=[{"role":"system","content":SYSTEM_MSG},
                      {"role":"user",  "content":"\n\n---\n\n".join(payloads)}],
        ).choices[0].message.content.strip()

        raw_parts.append(gpt_reply)

        for blk, letter in zip(BLOCK_SPLIT.split(gpt_reply), letters):
            try:
                records.append(parse_block(blk, letter))
            except ValueError:
                st.warning("Skipped malformed block.")

    raw_text = "\n\n".join(raw_parts)

    st.download_button("📥 gpt_blocks.txt", raw_text.encode(),
                       "gpt_blocks.txt", "text/plain")
    st.download_button("📥 mcq_output.json",
                       json.dumps(records, indent=2, ensure_ascii=False).encode(),
                       "mcq_output.json", "application/json")

    st.success(f"{len(records)} questions processed!")
    st.code(json.dumps(records[:2], indent=2, ensure_ascii=False) + "\n…",
            language="json")
