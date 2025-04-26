# streamlit_app.py  –  regex with GPT fallback
# ----------------------------------------------------------
import json, re, textwrap
from datetime import datetime, timezone
import openai, streamlit as st

openai.api_key = st.secrets["openai_api_key"]
MODEL = "gpt-4o"
QUESTIONS_PER_BATCH = 8          # for the expensive “full” prompt later

# ---------- 1. Regex that handles the usual pattern ----------
Q_RE = re.compile(
    r"^\s*(\d+)\.\s*(.*?)\s*\((?:a|A)\)\s*(.*?)\s*\((?:b|B)\)\s*(.*?)\s*"
    r"\((?:c|C)\)\s*(.*?)\s*\((?:d|D)\)\s*(.*?)\s*$",
    re.M | re.S,
)
A_RE = re.compile(r"(\d+)\s*\.\s*([A-Ea-e])")

LETTER2FIELD = {"A": "option_a", "B": "option_b", "C": "option_c",
                "D": "option_d", "E": "option_e"}

# ---------- 2. Mini-prompt used *only* for failures ----------
PARSE_PROMPT = textwrap.dedent("""
    Extract the stem and four options from this text.
    Return JSON: {"stem":"...", "A":"...", "B":"...", "C":"...", "D":"..."}
""")

def gpt_extract(raw_question: str):
    try:
        rsp = openai.chat.completions.create(
            model=MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": PARSE_PROMPT},
                {"role": "user",   "content": raw_question},
            ],
            max_tokens=120,
        )
        return json.loads(rsp.choices[0].message.content)
    except Exception:
        return None

# ---------- 3. Prompt for full clean-up & option E ----------
FULL_PROMPT_SYS = """
You are an expert medical-education content formatter.
For each MCQ, output:

STEM: <cleaned stem>
A: <cleaned A>  B: <cleaned B>  C: <cleaned C>  D: <cleaned D>
E: <plausible but incorrect new distractor>
DIFF: <easy|medium|hard>
EXP: <≤80 words explanation>

✱ Exactly one correct answer (given separately by the user).
✱ No extra commentary.
"""

FULL_USER_TEMPLATE = """Q: {stem}
A) {A}  B) {B}  C) {C}  D) {D}
Correct Letter: {letter}
"""

# ---------- 4. Streamlit UI ----------
st.title("🧠 MCQ → JSON (regex + GPT fallback)")

raw_q = st.text_area("QUESTIONS block", height=300)
raw_a = st.text_area("ANSWERS block", height=100)

if st.button("Generate JSON"):
    if not raw_q.strip() or not raw_a.strip():
        st.error("Both blocks are required.")
        st.stop()

    ans_map = {int(n): l.upper() for n, l in A_RE.findall(raw_a)}

    # 4·1  Split text roughly by “n.” header
    chunks = re.split(r"\n(?=\d+\.)", raw_q.strip())
    parsed = []
    needs_gpt = []

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

    # 4·2  Send only the failures to GPT-extract
    for bad in needs_gpt:
        res = gpt_extract(bad)
        if res:
            num_match = re.match(r"^\s*(\d+)", bad)
            parsed.append(
                {
                    "number": int(num_match.group(1)) if num_match else -1,
                    "stem": res["stem"],
                    "A": res["A"],
                    "B": res["B"],
                    "C": res["C"],
                    "D": res["D"],
                }
            )
        else:
            st.warning(f"Skipped one malformed question:\n{bad[:60]}…")

    # 4·3  Clean up & add option E via GPT (batched)
    parsed.sort(key=lambda x: x["number"])
    final_recs, batch = [], []

    def flush(batch_items):
        if not batch_items:
            return
        batch_prompt = "\n\n---\n\n".join(batch_items)
        rsp = openai.chat.completions.create(
            model=MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": FULL_PROMPT_SYS},
                {"role": "user",   "content": batch_prompt},
            ],
        ).choices[0].message.content
        return rsp.split("\n\n")

    for q in parsed:
        letter = ans_map.get(q["number"], "")
        user_block = FULL_USER_TEMPLATE.format(**q, letter=letter)
        batch.append(user_block)
        if len(batch) == QUESTIONS_PER_BATCH:
            for blk, q0 in zip(flush(batch), batch):
                num = int(q0.split()[1].rstrip(":"))
                final_recs.append(blocks_to_record(blk, ans_map[num]))
            batch = []

    # leftovers
    if batch:
        for blk, q0 in zip(flush(batch), batch):
            num = int(q0.split()[1].rstrip(":"))
            final_recs.append(blocks_to_record(blk, ans_map[num]))

    # stamp and download
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in final_recs:
        r["created_at"] = ts

    out = json.dumps(final_recs, indent=2, ensure_ascii=False)
    st.download_button("📥 Download mcq_output.json", out,
                       file_name="mcq_output.json", mime="application/json")
    st.success(f"{len(final_recs)} questions processed ("
               f"{len(needs_gpt)} via GPT fallback).")
    st.code(out[:1000] + "\n…", language="json")
