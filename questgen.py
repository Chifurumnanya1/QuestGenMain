# streamlit_app.py
# ────────────────────────────────────────────────────────────────
"""
MCQ → Supabase JSON (regex + GPT fallback, fixed batching bug)

• QUESTIONS box:  1. text (a)…(d)…
• ANSWERS  box:   1. C 2. A …

Pipeline
1. Regex pulls stem + A-D; questions it can’t parse go to a tiny GPT “extract” prompt.
2. All items are then sent (batched) to GPT-4o to:
   • rewrite grammar   • add a new wrong option E
   • label difficulty   • write ≤80-word explanation
3. JSON is assembled locally and offered for download.

Token cost ≈ 55/output token per MCQ for the clean-up step;
fallback parses pay ~20 tokens each.
"""

import json, re, textwrap
from datetime import datetime, timezone
import openai, streamlit as st

# ─────────── Config ───────────
openai.api_key = st.secrets["openai_api_key"]
MODEL = "gpt-4o"
QUESTIONS_PER_BATCH = 8          # tweak if needed
# ──────────────────────────────

# ---------- 1. Regex pattern ----------
Q_RE = re.compile(
    r"^\s*(\d+)\.\s*(.*?)\s*\((?:a|A)\)\s*(.*?)\s*\((?:b|B)\)\s*(.*?)\s*"
    r"\((?:c|C)\)\s*(.*?)\s*\((?:d|D)\)\s*(.*?)\s*$",
    re.M | re.S,
)
A_RE = re.compile(r"(\d+)\s*\.\s*([A-Ea-e])")

LETTER2FIELD = {"A": "option_a", "B": "option_b", "C": "option_c",
                "D": "option_d", "E": "option_e"}

# ---------- 2. Mini-prompt for regex failures ----------
PARSE_PROMPT = textwrap.dedent("""
    Extract the stem and four options from this text.
    Return JSON: {"stem":"...", "A":"...", "B":"...", "C":"...", "D":"..."}
""")

def gpt_extract(raw_question: str):
    try:
        rsp = openai.chat.completions.create(
            model=MODEL,
            temperature=0.0,
            messages=[{"role": "system", "content": PARSE_PROMPT},
                      {"role": "user",   "content": raw_question}],
            max_tokens=120,
        )
        return json.loads(rsp.choices[0].message.content)
    except Exception:
        return None

# ---------- 3. Prompt for clean-up + option E ----------
FULL_SYS = """
You are an expert medical-education formatter.
For each MCQ, output:

STEM: <cleaned stem>
A: <A>  B: <B>  C: <C>  D: <D>
E: <plausible but incorrect distractor>
DIFF: <easy|medium|hard>
EXP: <≤80 words explanation>

✱ Do NOT repeat the correct letter in the options.
✱ Keep meaning intact, only fix grammar/clarity.
✱ Separate multiple MCQs with one blank line.
"""

USER_TMPL = """Q: {stem}
A) {A}  B) {B}  C) {C}  D) {D}
Correct Letter: {letter}
"""

def blocks_to_record(block: str, correct_letter: str):
    rec = {}
    for line in block.splitlines():
        if line.startswith("STEM:"):
            rec["question_text"] = line[5:].strip()
        elif line[1:3] == ":" and line[0] in "ABCDE":
            rec[f"option_{line[0].lower()}"] = line[3:].strip()
        elif line.startswith("DIFF:"):
            rec["difficulty"] = line[5:].strip().lower()
        elif line.startswith("EXP:"):
            rec["explanation_text"] = line[4:].strip()
    rec["correct_answer"] = rec.get(LETTER2FIELD.get(correct_letter, ""), None)
    return rec

# ---------- 4. Streamlit UI ----------
st.title("🧠 MCQ → Supabase JSON (robust, low-token)")

raw_q = st.text_area("QUESTIONS block", height=300)
raw_a = st.text_area("ANSWERS block", height=100)

if st.button("Generate JSON"):
    if not raw_q.strip() or not raw_a.strip():
        st.error("Both QUESTIONS and ANSWERS are required.")
        st.stop()

    ans_map = {int(n): l.upper() for n, l in A_RE.findall(raw_a)}

    # 4·1 Split roughly by newline + number.
    chunks = re.split(r"\n(?=\d+\.)", raw_q.strip())
    parsed, needs_gpt = [], []

    for ch in chunks:
        if m := Q_RE.match(ch):
            parsed.append(
                {
                    "number": int(m.group(1)),
                    "stem": m.group(2).strip(),
                    "A": m.group(3).strip(),
                    "B": m.group(4).strip(),
                    "C": m.group(5).strip(),
                    "D": m.group(6).strip(),
                }
            )
        else:
            needs_gpt.append(ch.strip())

    # 4·2 Send only failures to GPT-extract
    for bad in needs_gpt:
        res = gpt_extract(bad)
        if res:
            num_match = re.match(r"^\s*(\d+)", bad)
            parsed.append(
                {
                    "number": int(num_match.group(1)) if num_match else -1,
                    "stem": res["stem"],
                    "A": res["A"], "B": res["B"], "C": res["C"], "D": res["D"],
                }
            )
        else:
            st.warning(f"Skipped one malformed question:\n{bad[:60]}…")

    # 4·3 Clean-up & add option E (batched, fixed indexing)
    parsed.sort(key=lambda x: x["number"])
    final_recs, batch_pairs = [], []

    def flush(pairs):
        if not pairs:
            return []
        text_blob = "\n\n---\n\n".join(p[1] for p in pairs)
        resp = openai.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            messages=[{"role": "system", "content": FULL_SYS},
                      {"role": "user",   "content": text_blob}],
        ).choices[0].message.content
        return resp.split("\n\n")

    for q in parsed:
        letter = ans_map.get(q["number"], "")
        user_block = USER_TMPL.format(**q, letter=letter)
        batch_pairs.append((q["number"], user_block))
        if len(batch_pairs) == QUESTIONS_PER_BATCH:
            for blk, (num, _) in zip(flush(batch_pairs), batch_pairs):
                final_recs.append(blocks_to_record(blk, ans_map[num]))
            batch_pairs = []

    if batch_pairs:
        for blk, (num, _) in zip(flush(batch_pairs), batch_pairs):
            final_recs.append(blocks_to_record(blk, ans_map[num]))

    # 5. stamp & download
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in final_recs:
        r["created_at"] = ts

    out_json = json.dumps(final_recs, indent=2, ensure_ascii=False)
    st.download_button("📥 Download mcq_output.json", out_json,
                       file_name="mcq_output.json", mime="application/json")
    st.success(f"{len(final_recs)} questions processed "
               f"({len(needs_gpt)} via GPT fallback).")
    st.code(out_json[:1000] + "\n…", language="json")
