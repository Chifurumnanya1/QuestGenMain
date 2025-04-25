# ───────────────────────────────────────────────────────────────
# app.py  –  Textbook ➜ FAISS-RAG ➜ MCQ JSON ➜ Supabase RPC
# (OpenAI Python SDK ≥ 1.15)
# ───────────────────────────────────────────────────────────────
import streamlit as st, json, datetime as dt, re, os, tempfile, uuid, requests
from pathlib import Path
import faiss
from openai import OpenAI                                   # NEW SDK v1 client

# ─── 1.  Secrets / keys ───────────────────────────────────────
openai_api_key = st.secrets["openai_api_key"]
supabase_url   = st.secrets["supabase_url"]
supabase_key   = st.secrets["supabase_key"]
rpc_name       = "upload_questions"                    # ← change

client = OpenAI(api_key=openai_api_key)                      # NEW

# ─── 2.  Llama-Index + FAISS imports ─────────────────────────
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as LlamaOpenAI
from llama_index.vector_stores.faiss import FaissVectorStore

# ─── 3.  Streamlit UI ────────────────────────────────────────
st.set_page_config("Textbook ➜ MCQ Generator", "📚", layout="centered")
st.title("Textbook ➜ MCQ JSON Generator 🚀")

upl  = st.file_uploader("Upload PDF / DOCX / TXT", ["pdf", "docx", "txt"])
subj = st.text_input("Subject name")
chap = st.text_input("Chapter name")
topic= st.text_input("Topic / keyword")
num  = st.number_input("How many MCQs?", 1, 50, 10)
if "idx" not in st.session_state: st.session_state.idx = None

# ─── 4.  Build FAISS index helper ────────────────────────────
def build_index(path: Path):
    docs  = SimpleDirectoryReader(input_files=[str(path)]).load_data()
    embed = OpenAIEmbedding(model="text-embedding-3-small")
    svc   = ServiceContext.from_defaults(
        llm=LlamaOpenAI(model="gpt-3.5-turbo", temperature=0),
        embed_model=embed,
    )
    dim   = len(embed.get_text_embedding("probe"))
    fidx  = faiss.IndexFlatL2(dim)
    store = FaissVectorStore(fidx)
    return VectorStoreIndex.from_documents(docs, service_context=svc,
                                           vector_store=store)

if upl:
    with tempfile.TemporaryDirectory() as tmp:
        tmpf = Path(tmp)/f"{uuid.uuid4()}{Path(upl.name).suffix}"
        with open(tmpf,"wb") as f: f.write(upl.getbuffer())
        st.session_state.idx = build_index(tmpf)
        st.success("✅ FAISS index built!")

# ─── 5.  MCQ generation (uses new client) ────────────────────
SCHEMA = """{ "question_text": "string","option_a":"string","option_b":"string",
"option_c":"string","option_d":"string","option_e":"string","correct_answer":"string",
"explanation_text":"string","difficulty":"easy|medium|hard","created_at":"" }""".strip()

SYSTEM = ("You are an MCQ generator.\nReturn ONLY valid JSON (array of objects) "
          "conforming exactly to this schema:\n" + SCHEMA)

def prompt(txt,n): return (f"Generate {n} five-option MCQs from the passage below. "
                           "correct_answer must equal one of option_a-e verbatim.\n\n\"\"\""
                           + txt + "\"\"\"")

def make_mcqs(txt,n):
    comp = client.chat.completions.create(                  # NEW CALL
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":SYSTEM},
            {"role":"user",  "content":prompt(txt,n)},
        ],
        temperature=0.3,
    )
    resp = comp.choices[0].message.content.strip()          # NEW ACCESS
    data = json.loads(resp)
    for q in data:
        key = q.get("correct_answer","")
        if key in ["option_a","option_b","option_c","option_d","option_e"]:
            q["correct_answer"] = q.get(key,"")
        q["created_at"] = dt.datetime.utcnow().isoformat()
    return data

# ─── 6.  Retrieve ➜ MCQs ➜ Supabase ──────────────────────────
if st.button("🔍 Retrieve & Generate"):
    if not st.session_state.idx: st.warning("Upload textbook first."); st.stop()
    if not topic.strip():        st.warning("Enter a topic."); st.stop()
    if not (subj and chap):      st.warning("Fill subject & chapter."); st.stop()

    with st.spinner("Searching …"):
        passage = st.session_state.idx.as_query_engine(similarity_top_k=5)\
                                     .query(topic).response
    with st.spinner("Generating MCQs …"):
        mcqs = make_mcqs(passage, int(num))

    st.success(f"Generated {len(mcqs)} MCQs"); st.json(mcqs, expanded=False)

    fname = f"{re.sub(r'[^\w\\-. ]','_',topic)}_{dt.datetime.utcnow():%Y%m%d_%H%M%S}.json"
    with open(fname,"w",encoding="utf-8") as f: json.dump(mcqs,f,indent=2)
    with open(fname,"rb") as f: st.download_button("Download JSON", f, fname)

    if st.button("📤 Send to Supabase"):
        payload = {
            "_subject_name": subj,
            "_chapter_name": chap,
            "_topic_name":   topic.strip(),
            "_questions":    json.dumps(mcqs)
        }
        hdrs = {
            "apikey":supabase_key,
            "Authorization":f"Bearer {supabase_key}",
            "Content-Type":"application/json"
        }
        url = f"{supabase_url}/rest/v1/rpc/{rpc_name}"
        with st.spinner("Uploading …"):
            try:
                r = requests.post(url,json=payload,headers=hdrs,timeout=30)
                r.raise_for_status()
                st.success("🎉 Uploaded to Supabase!")
                if r.content: st.json(r.json())
            except requests.RequestException as e:
                st.error(f"RPC failed:\n{e}")
