# ────────────────────────────────────────────────────────────────
# app.py  –  Textbook ➜ Vector-RAG ➜ MCQ JSON ➜ Supabase RPC
# ────────────────────────────────────────────────────────────────
import streamlit as st
import openai, json, datetime as dt, re, os, tempfile, uuid, requests
from pathlib import Path

# ─── 1.  Secrets / keys ─────────────────────────────────────────
openai_api_key = st.secrets.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
supabase_url   = st.secrets.get("supabase_url")   or os.getenv("SUPABASE_URL")
supabase_key   = st.secrets.get("supabase_key")   or os.getenv("SUPABASE_KEY")
rpc_name       = "upload_questions"          # ← change to exact name

if not (openai_api_key and supabase_url and supabase_key):
    st.error("❌ Missing OpenAI or Supabase credentials."); st.stop()
openai.api_key = openai_api_key
os.environ["OPENAI_API_KEY"] = openai_api_key      # LlamaIndex uses env

# ─── 2.  LlamaIndex + FAISS imports (new layout) ───────────────
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    ServiceContext,
)
from llama_index.core.embeddings import OpenAIEmbedding
from llama_index.core.llms import OpenAI as LlamaOpenAI
from llama_index.vector_stores.faiss import FaissVectorStore

# ─── 3.  Streamlit page config ─────────────────────────────────
st.set_page_config("Textbook ➜ MCQ Generator", "📚", layout="centered")
st.title("Textbook ➜ MCQ JSON Generator 🚀")

# ─── 4.  UI inputs ─────────────────────────────────────────────
uploaded = st.file_uploader("Upload PDF / DOCX / TXT", ["pdf", "docx", "txt"])
subject  = st.text_input("Subject name")
chapter  = st.text_input("Chapter name")
topic    = st.text_input("Topic / keyword to search")
num_qs   = st.number_input("How many MCQs?", 1, 50, 10)

# session placeholders for index + store
if "idx" not in st.session_state:   st.session_state.idx  = None
if "vs"  not in st.session_state:   st.session_state.vs   = None

# ─── 5.  Build FAISS index from upload ─────────────────────────
def build_faiss_index(file_path: Path):
    docs = SimpleDirectoryReader(input_files=[str(file_path)]).load_data()
    svc  = ServiceContext.from_defaults(
        llm=LlamaOpenAI(model="gpt-3.5-turbo", temperature=0),
        embed_model=OpenAIEmbedding(model="text-embedding-3-small"),
    )
    store = FaissVectorStore()
    idx   = VectorStoreIndex.from_documents(docs,
                                            service_context=svc,
                                            vector_store=store)
    return idx, store

if uploaded:
    with tempfile.TemporaryDirectory() as tmp:
        ext = Path(uploaded.name).suffix
        tmp_file = Path(tmp)/f"{uuid.uuid4()}{ext}"
        with open(tmp_file,"wb") as f: f.write(uploaded.getbuffer())
        idx, store = build_faiss_index(tmp_file)
        st.session_state.idx, st.session_state.vs = idx, store
        st.success("✅ Vector index built!")

# ─── 6.  MCQ generation helpers ────────────────────────────────
SCHEMA = """
{
  "question_text": "string",
  "option_a": "string",
  "option_b": "string",
  "option_c": "string",
  "option_d": "string",
  "option_e": "string",
  "correct_answer": "string",
  "explanation_text": "string",
  "difficulty": "easy|medium|hard",
  "created_at": ""
}
""".strip()

SYSTEM_PROMPT = (
    "You are an MCQ generator.\n"
    "Return ONLY valid JSON — an array of objects. Every object must match exactly this schema:\n"
    + SCHEMA + "\nDo NOT wrap the JSON in markdown or add any extra keys."
)

def mcq_prompt(passage:str, n:int)->str:
    return (
        f"Generate {n} five-option MCQs from the passage below. "
        "The correct_answer field must equal one of option_a-e verbatim.\n\n"
        '\"\"\"' + passage + '\"\"\"'
    )

def generate_mcqs(text:str, n:int):
    res = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":mcq_prompt(text,n)}
        ],
        temperature=0.3,
    ).choices[0].message.content.strip()
    data = json.loads(res)            # raises if invalid
    # patch correct_answer placeholders
    for q in data:
        key = q.get("correct_answer","")
        if key in ["option_a","option_b","option_c","option_d","option_e"]:
            q["correct_answer"] = q.get(key,"")
        q["created_at"] = dt.datetime.utcnow().isoformat()
    return data

# ─── 7.  Main button: retrieve -> MCQs -> Supabase ─────────────
if st.button("🔍 Retrieve & Generate"):
    if not st.session_state.idx:
        st.warning("Upload a textbook first."); st.stop()
    if not topic.strip():
        st.warning("Enter a topic to search."); st.stop()
    if not (subject and chapter):
        st.warning("Fill in subject & chapter."); st.stop()

    with st.spinner("Retrieving relevant content …"):
        qe   = st.session_state.idx.as_query_engine(similarity_top_k=5)
        ans  = qe.query(topic)
        passage = ans.response

    with st.spinner("Generating MCQs …"):
        try:
            mcqs = generate_mcqs(passage, int(num_qs))
        except Exception as e:
            st.error(f"MCQ generation failed:\n{e}"); st.stop()

    st.success(f"✅ Generated {len(mcqs)} MCQs")
    st.json(mcqs, expanded=False)

    # local download
    ts   = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fkey = re.sub(r"[^\w\-. ]","_", topic) or "mcq"
    fname= f"{fkey}_{ts}.json"
    with open(fname,"w",encoding="utf-8") as f: json.dump(mcqs,f,indent=2)
    with open(fname,"rb") as f: st.download_button("Download JSON",f,fname)

    # push to Supabase
    if st.button("📤 Send to Supabase"):
        pl = {
            "_subject_name": subject,
            "_chapter_name": chapter,
            "_topic_name":   topic.strip(),
            "_questions":    json.dumps(mcqs),
        }
        hdr= {"apikey":supabase_key,
              "Authorization":f"Bearer {supabase_key}",
              "Content-Type":"application/json"}
        url=f"{supabase_url}/rest/v1/rpc/{rpc_name}"
        with st.spinner("Uploading …"):
            try:
                r = requests.post(url,json=pl,headers=hdr,timeout=30)
                r.raise_for_status()
                st.success("🎉 Uploaded to Supabase!")
                if r.content: st.json(r.json())
            except requests.RequestException as e:
                st.error(f"RPC failed:\n{e}")
                st.text(r.text if 'r' in locals() else "")
