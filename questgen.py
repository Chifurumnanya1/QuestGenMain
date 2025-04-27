import streamlit as st
from openai import OpenAI
import pandas as pd
import json, re, textwrap
from datetime import datetime
from io import StringIO, BytesIO

# ── OpenAI init ───────────────────────────────────────────────────────────────
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

SYSTEM_PROMPT = """
You are an expert MCQ formatter.
Return ONLY a valid JSON array (no markdown) where each element has:
"id","question_text","difficulty","correct_answer",
"option_a","option_b","option_c","option_d","option_e",
"explanation_text","created_at".
• Fix grammar, invent a wrong option_e, generate a 1-2-sentence explanation.
• difficulty="easy", created_at="".
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def chat(prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role":"system","content":SYSTEM_PROMPT},
                  {"role":"user",  "content":prompt}],
        temperature=0.15, max_tokens=4000)
    return resp.choices[0].message.content.strip()

def parse_keys(raw: str) -> dict[int,str]:
    m={}
    for piece in re.findall(r'(\d+\.[A-Ea-e])', raw):
        q,ans = piece.split('.'); m[int(q)]=ans.upper()
    return m

def chunk(lst,n):
    for i in range(0,len(lst),n): yield lst[i:i+n],i

# ── UI ────────────────────────────────────────────────────────────────────────
st.set_page_config("MCQ → JSON", "🗂", layout="wide")
st.title("🗂 MCQ Cleaner → JSON")

batch_sz = st.sidebar.selectbox("Batch size", [20,30,40,50], 1)

raw_mcq = st.text_area("Paste raw MCQs", height=300)
raw_key = st.text_area("Paste answer keys  (e.g. 1.B 2.A …)", height=100)

if st.button("Generate JSON"):
    if not raw_mcq.strip() or not raw_key.strip():
        st.warning("Please paste MCQs and answer keys"); st.stop()

    blocks   = [b.strip() for b in re.split(r'\n(?=\d+\.)',raw_mcq) if b.strip()]
    keys_map = parse_keys(raw_key)

    all_rows=[]; next_id=1; missing=[]
    for chunk_mcq,off in chunk(blocks,batch_sz):
        start=off+1; end=start+len(chunk_mcq)-1
        key_subset=" ".join(f"{i}.{keys_map.get(i,'')}"
                            for i in range(start,end+1) if i in keys_map)
        user_prompt = f"MCQs:\n{'\n'.join(chunk_mcq)}\n\nAnswers:\n{key_subset}"
        with st.spinner(f"Batch {start}-{end}"):
            raw_json = chat(user_prompt)

        try:
            rows = json.loads(raw_json)
            if len(rows)!=len(chunk_mcq): raise ValueError
        except Exception:
            missing.extend(range(start,end+1)); continue

        # patch id sequence
        for r in rows:
            r["id"]=next_id; next_id+=1
        all_rows.extend(rows)

    if missing:
        st.error(f"⚠️ Still missing MCQs: {missing[:10]}{'…' if len(missing)>10 else ''}")

    # download + preview
    json_data = json.dumps(all_rows, ensure_ascii=False, indent=2)
    st.download_button("📥 Download JSON",
                       data=json_data,
                       file_name=f"mcqs_{datetime.utcnow():%Y%m%d_%H%M%S}.json",
                       mime="application/json")
    st.subheader("Preview")
    st.json(all_rows[: min(50,len(all_rows))])
