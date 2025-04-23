# app.py
import streamlit as st
import openai, json, datetime as dt, re, os, tempfile, requests, uuid
from pathlib import Path

# ───────────────────────
# 1.  API / env setup
# ───────────────────────
openai_api_key = st.secrets.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
supabase_url   = st.secrets.get("supabase_url")   or os.getenv("SUPABASE_URL")
supabase_key   = st.secrets.get("supabase_key")   or os.getenv("SUPABASE_KEY")

if not (openai_api_key and supabase_url and supabase_key):
    st.error("Missing OpenAI or Supabase credentials in secrets / env.")
    st.stop()

openai.api_key = openai_api_key   # for explicit OpenAI calls
os.environ["OPENAI_API_KEY"] = openai_api_key   # LlamaIndex reads from env

# ───────────────────────
# 2.  LlamaIndex imports
# ───────────────────────
from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as LlamaOpenAI

# ───────────────────────
# 3.  Page config
# ───────────────────────
st.set_page_config("Textbook ➜ MCQ Generator", "📚", layout="centered")
st.title("Textbook ➜ MCQ JSON Generator 🚀")

# ───────────────────────
# 4.  UI inputs
# ───────────────────────
uploaded_file = st.file_uploader(
    "Upload textbook (PDF, DOCX, or TXT)",
    type=["pdf", "docx", "txt"]
)

subject_name  = st.text_input("Subject Name")
chapter_name  = st.text_input("Chapter Name")
topic_name    = st.text_input("Topic / Keyword to search")
num_qs        = st.number_input("How many MCQs?", 1, 50, 10)

# Session state helpers
if "index" not in st.session_state:          # LlamaIndex object
    st.session_state.index = None
if "doc_path" not in st.session_state:       # path of saved upload
    st.session_state.doc_path = None

# ───────────────────────
# 5.  Build / load index
# ───────────────────────
def build_index(file_path: Path):
    reader = SimpleDirectoryReader(input_files=[str(file_path)])
    docs   = reader.load_data()
    
    # Smaller models work fine for retrieval; adjust if desired
    service_context = ServiceContext.from_defaults(
        llm      = LlamaOpenAI(model="gpt-3.5-turbo", temperature=0),
        embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    )
    return VectorStoreIndex.from_documents(docs, service_context=service_context)

if uploaded_file:
    with tempfile.TemporaryDirectory() as tmp:
        file_ext  = Path(uploaded_file.name).suffix
        save_path = Path(tmp) / f"{uuid.uuid4()}{file_ext}"
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.session_state.index = build_index(save_path)
        st.session_state.doc_path = save_path
        st.success("✅ Index built from uploaded textbook!")

# ───────────────────────
# 6.  MCQ generation logic
# ───────────────────────
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
    + SCHEMA +
    "\nDo NOT wrap the JSON in markdown or add any extra keys."
)

def user_prompt(text:str, n:int)->str:
    return (
        f"Generate {n} five-option MCQs from the passage below. "
        "The correct_answer field must equal one of option_a-e verbatim.\n\n"
        '"""' + text + '"""'
    )

def generate_mcqs(passage:str, n:int):
    resp = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[
            {"role":"system", "content": SYSTEM_PROMPT},
            {"role":"user",   "content": user_prompt(passage, n)}
        ],
        temperature=0.3,
    ).choices[0].message.content.strip()
    try:
        data = json.loads(resp)
    except json.JSONDecodeError:
        raise ValueError(f"Bad JSON from OpenAI:\n{resp}")

    for q in data:
        key = q.get("correct_answer","")
        if key in ["option_a","option_b","option_c","option_d","option_e"]:
            q["correct_answer"] = q.get(key,"")
        q["created_at"] = dt.datetime.utcnow().isoformat()

    return data

# ───────────────────────
# 7.  Main action button
# ───────────────────────
if st.button("🔍 Retrieve ➜ Generate MCQs"):
    if not st.session_state.index:
        st.warning("Please upload a textbook first."); st.stop()
    if not topic_name.strip():
        st.warning("Enter a topic / keyword to search."); st.stop()
    if not (subject_name and chapter_name):
        st.warning("Enter subject and chapter names."); st.stop()

    # 1. Retrieve relevant passage(s)
    with st.spinner("Retrieving relevant content …"):
        query_engine = st.session_state.index.as_query_engine(similarity_top_k=5)
        retrieval    = query_engine.query(topic_name)
        passage      = retrieval.response

    # 2. Generate MCQs
    with st.spinner("Generating MCQs …"):
        try:
            mcqs = generate_mcqs(passage, num_qs)
        except ValueError as e:
            st.error(str(e)); st.stop()

    # 3. Show + download JSON
    timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_topic= re.sub(r"[^\w\-. ]","_", topic_name.strip())
    file_name = f"{safe_topic}_{timestamp}.json"

    st.success(f"✅ Generated {len(mcqs)} MCQs")
    st.json(mcqs, expanded=False)

    with open(file_name,"w",encoding="utf-8") as f:
        json.dump(mcqs,f,ensure_ascii=False,indent=2)
    with open(file_name,"rb") as f:
        st.download_button("Download JSON", f, file_name=file_name,
                           mime="application/json")

    # 4. Push to Supabase RPC
    if st.button("📤 Send to Supabase"):
        payload = {
            "_subject_name": subject_name,
            "_chapter_name": chapter_name,
            "_topic_name":   topic_name.strip(),
            "_questions":    json.dumps(mcqs)
        }
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json"
        }
        rpc_name = "your_rpc_function_name"      # ← change to actual
        rpc_url  = f"{supabase_url}/rest/v1/rpc/{rpc_name}"

        with st.spinner("Uploading to Supabase …"):
            try:
                res = requests.post(rpc_url, json=payload, headers=headers, timeout=30)
                res.raise_for_status()
                st.success("🎉 MCQs uploaded successfully!")
                if res.content:
                    st.json(res.json())
            except requests.exceptions.RequestException as e:
                st.error(f"Supabase RPC failed:\n{e}")
                st.text(res.text if 'res' in locals() else "")
