"""
Legal Assist+ : Translation Utilities (v2 -- Groq-based)
---------------------------------------------------------
REVISED: previously used deep-translator (an unofficial, free Google
Translate scraper), which hit persistent rate-limit errors (HTTP 429 /
TooManyRequests) during testing, even with retry logic.

This version translates using your EXISTING Groq connection instead --
no new API, no new library, no new rate-limit surface. Reuses the
proven, already-stable ask_llm() from analyze_document.py (which has
its own retry-with-backoff and empty-response handling built in).

Translation happens only at the edges: question in, answer out. The
core RAG pipeline (retrieval, main Groq LLM calls) never needs to know
about languages.
"""

from analyze_document import ask_llm

# Supported languages for this project (language name shown in UI -> code)
SUPPORTED_LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Marathi": "mr",
}

# Reverse mapping, code -> full language name (for building clear LLM prompts)
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
}

TRANSLATION_MODEL_MAX_TOKENS = 1500  # generous enough for a full legal answer


def _translate_via_groq(text, target_language_name, groq_client):
    """
    Core translation call -- asks the LLM to translate text, instructing
    it to return ONLY the translation, nothing else (no preamble, no
    explanation), so the output can be used directly in the UI.
    """
    prompt = f"""Translate the following text into {target_language_name}.
Output ONLY the translation itself -- no preamble, no explanation, no
quotation marks around it, nothing else.

TEXT TO TRANSLATE:
{text}

TRANSLATION:"""
    return ask_llm(prompt, groq_client, max_tokens=TRANSLATION_MODEL_MAX_TOKENS).strip()


def translate_to_english(text, source_language_code, groq_client):
    """
    Translates user input into English before it enters the RAG pipeline.
    If already English, returns the text unchanged (no wasted API call).
    """
    if source_language_code == "en" or not text.strip():
        return text
    try:
        return _translate_via_groq(text, "English", groq_client)
    except Exception as e:
        raise RuntimeError(f"Could not translate your question to English: {e}")


def translate_from_english(text, target_language_code, groq_client):
    """
    Translates the LLM's English answer into the user's selected language.
    If target is English, returns unchanged. If translation fails, returns
    the English answer with a clear note rather than crashing -- the user
    still gets a correct, useful answer, just not in their chosen language.
    """
    if target_language_code == "en" or not text.strip():
        return text
    try:
        target_name = LANGUAGE_NAMES.get(target_language_code, target_language_code)
        return _translate_via_groq(text, target_name, groq_client)
    except Exception as e:
        print(f"[Translation warning] Could not translate answer: {e}")
        return text + "\n\n*(Translation to your selected language failed -- showing English.)*"
