"""
Legal Assist+ : Streamlit UI Prototype (v2)
------------------------------------------------
Connects directly to your existing backend logic (analyze_document.py and
query_legal_assist.py). This version adds: persistent chat history (saved to
disk, survives restarts), a proper always-accessible Login tab, a professional
theme, and a defensive safety net against stray HTML in LLM output.

BEFORE RUNNING:
    pip install streamlit

Run with:
    streamlit run app.py

IMPORTANT: also place the included config.toml file at:
    .streamlit/config.toml
(create the .streamlit folder in your project root if it doesn't exist)
This sets the color theme -- without it, the app still works, just with
default Streamlit styling instead of the intended navy/blue theme.
"""

import re
import json
import html
from pathlib import Path

import streamlit as st

from analyze_document import (
    extract_text_from_pdf,
    split_into_clauses,
    embed_clauses,
    retrieve_clauses,
    retrieve_law,
    build_combined_prompt,
    ask_llm,
    review_clause_batch,
    check_missing_clauses,
    CLAUSE_BATCH_SIZE,
    load_everything,
)
from query_legal_assist import (
    retrieve as retrieve_general_law,
    build_prompt as build_general_prompt,
)
from translation_utils import (
    SUPPORTED_LANGUAGES,
    translate_to_english,
    translate_from_english,
)

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Legal Assist+", page_icon="⚖️", layout="wide")

RISK_COLORS = {
    "High": "#c0392b",
    "Medium": "#d97e2c",
    "Medium-High": "#c96a1f",
    "Low": "#b58e1f",
    "None": "#2e7d4f",
}

CHAT_HISTORY_FILE = Path("data/chat_history.json")

CUSTOM_CSS = """
<style>
    .stApp { background-color: #ffffff; }
    section[data-testid="stSidebar"] {
        background-color: #10233b;
    }
    section[data-testid="stSidebar"] * { color: #e8edf2 !important; }
    section[data-testid="stSidebar"] button {
        background-color: #1a3a5c !important;
        border: 1px solid #2c5580 !important;
        border-radius: 6px;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: #2c5580 !important;
    }
    h1, h2, h3 { color: #10233b; }
    .stChatMessage { border-radius: 10px; }
    div[data-testid="stExpander"] {
        border: 1px solid #dbe2ea;
        border-radius: 8px;
    }
    .stButton>button[kind="primary"] {
        background-color: #1a3a5c;
        border: none;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #2c5580;
    }
</style>
"""


# ---------------------------------------------------------
# PERSISTENT CHAT STORAGE (survives app restarts, unlike session_state alone)
# ---------------------------------------------------------
def load_chat_history():
    if CHAT_HISTORY_FILE.exists():
        try:
            with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"qa_history": [], "doc_qa_history": {}}
    return {"qa_history": [], "doc_qa_history": {}}


def save_chat_history():
    CHAT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "qa_history": st.session_state.qa_history,
        "doc_qa_history": st.session_state.doc_qa_history_by_doc,
    }
    with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clean_answer_text(text):
    """
    Defensive safety net: strips stray HTML tags the LLM might emit despite
    instructions not to, and converts <br> into real markdown line breaks
    so nothing shows up as literal '<br>' text in the UI.
    """
    if not text:
        return text
    text = re.sub(r"<br\s*/?>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)  # strip any other stray HTML tags
    return html.unescape(text)


def format_source_line(s):
    """Formats one retrieved source for display -- statute citation vs case judgment."""
    if s.get("chunk_type") == "judgment":
        return f"- **{s['act_name']}** *(Court Judgment)* -- {s['title']}"
    return f"- **{s['act_name']}**, Section {s['number']}: {s['title']}"


# ---------------------------------------------------------
# CACHED RESOURCE LOADING (runs once, not on every interaction)
# ---------------------------------------------------------
@st.cache_resource(show_spinner="Loading Legal Assist+ knowledge base...")
def get_resources():
    return load_everything()


law_index, law_chunks, embed_model, groq_client = get_resources()

# ---------------------------------------------------------
# SESSION STATE INIT
# ---------------------------------------------------------
if "initialized" not in st.session_state:
    saved = load_chat_history()
    st.session_state.qa_history = saved["qa_history"]
    st.session_state.doc_qa_history_by_doc = saved["doc_qa_history"]
    st.session_state.initialized = True

if "page" not in st.session_state:
    st.session_state.page = "welcome"
if "doc_clauses" not in st.session_state:
    st.session_state.doc_clauses = None
if "doc_embeddings" not in st.session_state:
    st.session_state.doc_embeddings = None
if "doc_name" not in st.session_state:
    st.session_state.doc_name = None
if "doc_review_done" not in st.session_state:
    st.session_state.doc_review_done = False
if "doc_review_results" not in st.session_state:
    st.session_state.doc_review_results = []
if "doc_missing_report" not in st.session_state:
    st.session_state.doc_missing_report = ""
if "logged_in_as" not in st.session_state:
    st.session_state.logged_in_as = None


def go_to(page_name):
    st.session_state.page = page_name


def current_doc_qa_history():
    """Follow-up Q&A history, scoped per document name, persisted to disk."""
    if not st.session_state.doc_name:
        return []
    return st.session_state.doc_qa_history_by_doc.get(st.session_state.doc_name, [])


st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------
# SIDEBAR (persistent navigation -- always includes Login/Account)
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("## ⚖️ Legal Assist+")
    st.caption("AI-powered legal information & document review for Indian law")
    st.divider()

    st.button("Home", use_container_width=True, on_click=go_to, args=("home",))
    st.button("Ask a Legal Question", use_container_width=True, on_click=go_to, args=("qa",))
    st.button("Analyze My Document", use_container_width=True, on_click=go_to, args=("doc",))

    st.divider()
    st.markdown("**Jurisdiction**")
    jurisdiction = st.selectbox(
        "Filter by state (optional)",
        ["All India (Central law only)", "Maharashtra"],
        label_visibility="collapsed",
        key="jurisdiction_select",
    )
    st.caption(
        "Central law always applies. Selecting a state also includes that "
        "state's specific laws. Currently only Maharashtra is available in "
        "our dataset -- more states coming soon."
    )

    st.divider()
    st.markdown("**Language**")
    st.selectbox(
        "Choose your language",
        list(SUPPORTED_LANGUAGES.keys()),
        label_visibility="collapsed",
        key="language_select",
    )
    st.caption(
        "Ask and receive answers in your chosen language. Retrieval and "
        "legal reasoning always happen in English internally, then the "
        "question and answer are translated at the edges."
    )

    st.divider()
    if st.session_state.logged_in_as:
        st.success(f"Signed in as **{st.session_state.logged_in_as}**")
        if st.button("Log Out", use_container_width=True):
            st.session_state.logged_in_as = None
            st.rerun()
    else:
        st.button("Login / Account", use_container_width=True, on_click=go_to, args=("welcome",))

    if st.session_state.doc_name:
        st.info(f"Document loaded:\n**{st.session_state.doc_name}**")

    with st.expander("About this project"):
        st.write(
            "Legal Assist+ answers legal questions and reviews your documents using "
            "Retrieval-Augmented Generation, grounded strictly in verified Indian legal "
            "sources (BNS, BNSS, BSA, Constitution, and more) -- with citations, not "
            "guesses."
        )

    st.divider()
    st.caption(
        "This tool provides legal *information*, not legal *advice*. "
        "Consult a qualified lawyer for decisions with serious consequences."
    )


# ---------------------------------------------------------
# PAGE: WELCOME / LOGIN
# ---------------------------------------------------------
def render_welcome():
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("# ⚖️ Legal Assist+")
        st.markdown("##### Making Indian law accessible, one question at a time")
        st.markdown("<br>", unsafe_allow_html=True)

        with st.container(border=True):
            email = st.text_input("Email", placeholder="you@example.com", key="login_email")
            st.text_input("Password", type="password", placeholder="********", key="login_password")
            st.button("Log In", use_container_width=True, disabled=True)
            st.caption("Full account system coming soon (Security phase, in progress)")
            st.divider()
            if st.button("Continue as Guest ->", use_container_width=True, type="primary"):
                st.session_state.logged_in_as = "Guest"
                go_to("home")
                st.rerun()


# ---------------------------------------------------------
# PAGE: HOME / DASHBOARD
# ---------------------------------------------------------
def render_home():
    st.markdown("# Welcome to Legal Assist+")
    st.markdown(
        "An AI legal assistant grounded in verified Indian law -- the Constitution, "
        "BNS, BNSS, BSA, and other Central and State Acts -- built to explain legal "
        "information clearly and review your own documents for risks."
    )
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### Ask a Legal Question")
            st.write(
                "Get clear, direct answers to questions about Indian law -- grounded "
                "strictly in real statutes, never guessed."
            )
            st.button("Start Asking ->", key="home_qa_btn", on_click=go_to, args=("qa",))

    with col2:
        with st.container(border=True):
            st.markdown("### Analyze My Document")
            st.write(
                "Upload your own contract or agreement. Legal Assist+ scans every "
                "clause, flags risks, and checks what protections might be missing."
            )
            st.button("Upload a Document ->", key="home_doc_btn", on_click=go_to, args=("doc",))

    st.markdown("<br>", unsafe_allow_html=True)
    st.info(
        "**Disclaimer:** Legal Assist+ provides legal information to help you "
        "understand your situation -- it does not replace professional legal advice."
    )


# ---------------------------------------------------------
# PAGE: LEGAL Q&A
# ---------------------------------------------------------
def render_qa():
    st.markdown("# Ask a Legal Question")
    st.caption("Answers are grounded only in verified Indian legal sources, with citations.")

    for entry in st.session_state.qa_history:
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant"):
            st.markdown(clean_answer_text(entry["answer"]))
            if entry["sources"]:
                with st.expander(f"Sources ({len(entry['sources'])})"):
                    for s in entry["sources"]:
                        st.markdown(format_source_line(s))

    question = st.chat_input("Ask about Indian law...")
    if question:
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            lang_code = SUPPORTED_LANGUAGES[st.session_state.language_select]
            retrieved = []
            try:
                with st.spinner("Searching legal sources and generating an answer..."):
                    # Translate the question to English before it enters the pipeline.
                    # Retrieval and the LLM always operate in English internally.
                    question_en = translate_to_english(question, lang_code, groq_client)

                    jur = "Central" if st.session_state.jurisdiction_select.startswith("All India") else st.session_state.jurisdiction_select  # FIXED: was None, which skipped filtering entirely instead of restricting to Central-only
                    retrieved = retrieve_general_law(question_en, law_index, law_chunks, embed_model, jurisdiction_filter=jur)
                    prompt = build_general_prompt(question_en, retrieved)
                    raw_answer = ask_llm(prompt, groq_client, max_tokens=1500)
                    answer_en = clean_answer_text(raw_answer)

                    # Translate the finished English answer into the user's chosen language.
                    answer = translate_from_english(answer_en, lang_code, groq_client)
                st.markdown(answer)
                if retrieved:
                    with st.expander(f"Sources ({len(retrieved)})"):
                        for s in retrieved:
                            st.markdown(format_source_line(s))
            except RuntimeError as e:
                answer = f"⚠️ {e}"
                st.error(answer)

        st.session_state.qa_history.append(
            {"question": question, "answer": answer, "sources": retrieved}
        )
        save_chat_history()


# ---------------------------------------------------------
# PAGE: DOCUMENT ANALYSIS
# ---------------------------------------------------------
def parse_risk_counts(review_texts):
    counts = {"High": 0, "Medium": 0, "Medium-High": 0, "Low": 0, "None": 0}
    for text in review_texts:
        for level in counts:
            counts[level] += len(re.findall(rf"Risk:\s*\*?\*?{level}\b", text))
    return counts


def render_doc():
    st.markdown("# Analyze My Document")
    st.caption("Upload a contract or agreement. Legal Assist+ reviews it clause by clause.")

    uploaded_file = st.file_uploader("Upload a PDF document", type=["pdf"])

    if uploaded_file and uploaded_file.name != st.session_state.doc_name:
        with st.spinner("Extracting and splitting your document into clauses..."):
            raw_text = extract_text_from_pdf(uploaded_file)
            clauses = split_into_clauses(raw_text)
            clause_embeddings = embed_clauses(clauses, embed_model)

        st.session_state.doc_name = uploaded_file.name
        st.session_state.doc_clauses = clauses
        st.session_state.doc_embeddings = clause_embeddings
        st.session_state.doc_review_done = False
        st.session_state.doc_review_results = []
        st.session_state.doc_missing_report = ""
        st.success(f"Found {len(clauses)} clauses in your document.")

    if st.session_state.doc_clauses and not st.session_state.doc_review_done:
        if st.button("Run Full Review", type="primary"):
            clauses = st.session_state.doc_clauses
            progress = st.progress(0, text="Starting review...")
            results = []
            total_batches = (len(clauses) + CLAUSE_BATCH_SIZE - 1) // CLAUSE_BATCH_SIZE

            for i in range(0, len(clauses), CLAUSE_BATCH_SIZE):
                batch = clauses[i:i + CLAUSE_BATCH_SIZE]
                batch_num = i // CLAUSE_BATCH_SIZE + 1
                progress.progress(
                    batch_num / (total_batches + 1),
                    text=f"Reviewing clauses {batch[0]['clause_number']}-{batch[-1]['clause_number']}...",
                )
                findings = review_clause_batch(batch, law_index, law_chunks, embed_model, groq_client)
                results.append(clean_answer_text(findings))

            progress.progress(1.0, text="Checking for missing standard protections...")
            missing_report = clean_answer_text(check_missing_clauses(clauses, groq_client))

            st.session_state.doc_review_results = results
            st.session_state.doc_missing_report = missing_report
            st.session_state.doc_review_done = True
            progress.empty()
            st.rerun()

    if st.session_state.doc_review_done:
        results = st.session_state.doc_review_results
        counts = parse_risk_counts(results)

        st.markdown("### Review Summary")
        cols = st.columns(5)
        for col, (level, count) in zip(cols, counts.items()):
            with col:
                st.markdown(
                    f"<div style='text-align:center; padding:10px; border-radius:8px; "
                    f"background-color:{RISK_COLORS[level]}22; border:1px solid {RISK_COLORS[level]}'>"
                    f"<span style='font-size:28px; font-weight:bold; color:{RISK_COLORS[level]}'>{count}</span><br>"
                    f"<span style='font-size:13px;'>{level} Risk</span></div>",
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Clause-by-Clause Review")
        for i, findings in enumerate(results):
            with st.expander(f"Clause batch {i + 1}", expanded=(i == 0)):
                st.markdown(findings)

        st.markdown("### Missing Standard Protections")
        with st.container(border=True):
            st.markdown(st.session_state.doc_missing_report)

        st.info(
            "This is an automated risk scan to help you understand your document. "
            "It does not replace professional legal advice, especially for anything "
            "with significant financial or legal consequences."
        )

        st.markdown("---")
        st.markdown("### Ask About Your Document")

        for entry in current_doc_qa_history():
            with st.chat_message("user"):
                st.write(entry["question"])
            with st.chat_message("assistant"):
                st.markdown(clean_answer_text(entry["answer"]))

        doc_question = st.chat_input("Ask a question about your uploaded document...")
        if doc_question:
            with st.chat_message("user"):
                st.write(doc_question)
            with st.chat_message("assistant"):
                lang_code = SUPPORTED_LANGUAGES[st.session_state.language_select]
                translation_failed = False
                try:
                    with st.spinner("Checking your document and relevant law..."):
                        doc_question_en = translate_to_english(doc_question, lang_code, groq_client)

                        retrieved_clauses = retrieve_clauses(
                            doc_question_en, st.session_state.doc_clauses,
                            st.session_state.doc_embeddings, embed_model
                        )
                        jur = "Central" if st.session_state.jurisdiction_select.startswith("All India") else st.session_state.jurisdiction_select  # FIXED: was None, which skipped filtering entirely instead of restricting to Central-only
                        retrieved_law_results = retrieve_law(doc_question_en, law_index, law_chunks, embed_model, jurisdiction_filter=jur)
                        prompt = build_combined_prompt(doc_question_en, retrieved_clauses, retrieved_law_results)
                        raw_answer = ask_llm(prompt, groq_client, max_tokens=2048)
                        answer_en = clean_answer_text(raw_answer)

                        answer = translate_from_english(answer_en, lang_code, groq_client)
                    st.markdown(answer)
                except RuntimeError as e:
                    translation_failed = True
                    answer = f"⚠️ {e}"
                    st.error(answer)

            if not translation_failed:
                doc_name = st.session_state.doc_name
                if doc_name not in st.session_state.doc_qa_history_by_doc:
                    st.session_state.doc_qa_history_by_doc[doc_name] = []
                st.session_state.doc_qa_history_by_doc[doc_name].append(
                    {"question": doc_question, "answer": answer}
                )
                save_chat_history()

    elif not st.session_state.doc_clauses:
        st.info("Upload a PDF above to get started.")


# ---------------------------------------------------------
# ROUTER
# ---------------------------------------------------------
if st.session_state.page == "welcome":
    render_welcome()
elif st.session_state.page == "home":
    render_home()
elif st.session_state.page == "qa":
    render_qa()
elif st.session_state.page == "doc":
    render_doc()
