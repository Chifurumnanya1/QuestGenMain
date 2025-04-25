# ────────────────────────────────────────────────────────────────
# app.py  –  Textbook ➜ FAISS-RAG ➜ MCQ JSON ➜ Supabase RPC
# ────────────────────────────────────────────────────────────────
import streamlit as st, openai, json, datetime as dt, re, os, tempfile, uuid, requests
from pathlib import Path

# ─── 1.  Secrets / keys ─────────────────────────────────────────
openai_api_key = st.secrets.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
supabase_url   = st.secrets.get("supabase_url")   or os.getenv("SUPABASE_URL")
supabase_key   = st.secrets.get("supabase_key")   or os.getenv("SUPABASE_KEY")
rpc_name       = "your_rpc_function_name"          # ← change to actual name

if not (openai_api_key and supabase_url and supabase_key):
    st.error("❌ Missing OpenAI or Supabase credentials."); st.stop()
openai.api_key = openai_api_key
os.environ["OPENAI_API_KEY"] = openai_api_key

# ─── 2.  Llama-Index + FAISS imports ───────────────────────────
import faiss
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.storage import StorageContext          # ← fixed path
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as LlamaOpenAI
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
if "idx" not in st.session_state: st.session_state.idx = None

# ─── 5.  Build FAISS index ─────────────────────────────────────
def build_index(file_path: Path):
    docs = SimpleDirectoryReader(input_files=[str(file_path)]).load_data()

    embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    svc = ServiceContext.from_defaults(
        llm=LlamaOpenAI(model="gpt-3.5-turbo", temperature=0),
        embed_model=embed_model,
    )

    # determine embedding dimension
    dim = len(embed_model.get_text_embedding("probe"))
    faiss_index  = faiss.IndexFlatL2(dim)
    faiss_store  = FaissVectorStore(faiss_index)
    faiss_store.add(documents=docs)

    storage_ctx  = StorageContext.from_defaults(vector_store=faiss_store)
    return VectorStoreIndex(
        service_context=svc,
        storage_context=storage_ctx,
    )

if uploaded:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_file = Path(tmp) / f"{uuid.uuid4()}{Path(uploaded.name).suffix}"
        with open(tmp_file, "wb") as f:
            f.write(uploaded.getbuffer())
        st.session_state.idx = build_index(tmp_file)
        st.success("✅ FAISS vector index built!")

# ─── 6.  MCQ generation helpers ────────────────────────────────
SCHEMA = """
{ "question_text": "string", "option_a": "string", "option_b": "string",
  "option_c": "string", "option_d": "string", "option_e": "string",
  "correct_answer": "string", "explanation_text": "string",
  "difficulty": "easy|medium|hard", "created_at": "" }
""".strip()
SYSTEM_PROMPT = (
    "You are an MCQ generator.\nReturn ONLY valid JSON — an array of objects. "
    "Every object must match exactly this schema:\n" + SCHEMA +
    "\nDo NOT wrap the JSON in markdown or add any extra keys."
)
def build_prompt(txt:str,n:int)->str:
    return (f"Generate {n} five-option MCQs from the passage below. "
            "The correct_answer must equal one of option_a-e verbatim.\n\n\"\"\"" + txt + "\"\"\"")
def mcqs_from_text(txt:str,n:int):
    res = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"system","content":SYSTEM_PROMPT},
                  {"role":"user","content":build_prompt(txt,n)}],
        temperature=0.3,
    ).choices[0].message.content.strip()
    data = json.loads(res)
    for q in data:
        key = q.get("correct_answer","")
        if key in ["option_a","option_b","option_c","option_d","option_e"]:
            q["correct_answer"] = q.get(key,"")
        q["created_at"] = dt.datetime.utcnow().isoformat()
    return data

# ─── 7.  Retrieve ↦ MCQs ↦ Supabase ────────────────────────────
if st.button("🔍 Retrieve & Generate"):
    if not st.session_state.idx:   st.warning("Upload a textbook first."); st.stop()
    if not topic.strip():          st.warning("Enter a topic."); st.stop()
    if not (subject and chapter):  st.warning("Fill subject & chapter."); st.stop()

    with st.spinner("Retrieving content …"):
        passage = st.session_state.idx.as_query_engine(similarity_top_k=5).query(topic).response

    with st.spinner("Generating MCQs …"):
        mcqs = mcqs_from_text(passage, int(num_qs))

    st.success(f"✅ Generated {len(mcqs)} MCQs")
    st.json(mcqs, expanded=False)

    fname = f"{re.sub(r'[^\w\\-. ]','_',topic)}_{dt.datetime.utcnow():%Y%m%d_%H%M%S}.json"
    with open(fname, "w", encoding="utf-8") as f: json.dump(mcqs, f, indent=2)
    with open(fname, "rb") as f: st.download_button("Download JSON", f, fname)

    if st.button("📤 Send to Supabase"):
        payload = {
            "_subject_name": subject,
            "_chapter_name": chapter,
            "_topic_name":   topic.strip(),
            "_questions":    json.dumps(mcqs),
        }
        hdr = {
            "apikey":        supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type":  "application/json",
        }
        url = f"{supabase_url}/rest/v1/rpc/{rpc_name}"
        with st.spinner("Uploading …"):
            try:
                r = requests.post(url, json=payload, headers=hdr, timeout=30)
                r.raise_for_status()
                st.success("🎉 Uploaded to Supabase!")
                st.json(r.json() or {"status": "ok"})
            except requests.RequestException as e:
                st.error(f"RPC failed:\n{e}")
                st.text(r.text if 'r' in locals() else "")
