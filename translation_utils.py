"""
Legal Assist+ : Translation Utilities
-----------------------------------------
Wraps Google Translate (via the deep-translator library) so the core RAG
pipeline (retrieval, Groq LLM calls) never needs to know about languages --
translation happens only at the edges: question in, answer out.

BEFORE RUNNING:
    pip install deep-translator
"""

import time
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TooManyRequests


def _translate_with_retry(text, source, target, max_retries=2, wait_seconds=3):
    """
    Wraps GoogleTranslator().translate() with a short retry on rate-limit
    errors (deep-translator's free Google Translate wrapper is an
    unofficial method and gets throttled under rapid repeated use).
    """
    for attempt in range(max_retries):
        try:
            return GoogleTranslator(source=source, target=target).translate(text)
        except TooManyRequests:
            if attempt < max_retries - 1:
                time.sleep(wait_seconds)
            else:
                raise  # out of retries -- let the caller's except block handle it


# Supported languages for this project (language name shown in UI -> translate code)
SUPPORTED_LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Marathi": "mr",
}


def translate_to_english(text, source_language_code):
    """
    Translates user input into English before it enters the RAG pipeline.
    If already English, returns the text unchanged (no wasted API call).

    IMPORTANT: if translation fails (e.g. rate limit, no internet), this
    raises rather than silently falling back to the original text --
    searching untranslated non-English text against an English-only vector
    database produces misleading, essentially random results, which is
    worse than a clear error the UI can show the user.
    """
    if source_language_code == "en" or not text.strip():
        return text
    try:
        return _translate_with_retry(text, source_language_code, "en")
    except TooManyRequests:
        raise RuntimeError(
            "Translation service is temporarily rate-limited. Please wait a "
            "minute and try again, or switch the language back to English."
        )
    except Exception as e:
        raise RuntimeError(f"Could not translate your question to English: {e}")


def translate_from_english(text, target_language_code):
    """
    Translates the LLM's English answer into the user's selected language.
    If target is English, returns unchanged. If translation fails, returns
    the English answer with a clear note, rather than crashing -- the user
    still gets a correct, useful answer, just not in their chosen language.
    """
    if target_language_code == "en" or not text.strip():
        return text
    try:
        # Google Translate has a per-request character limit; split long
        # answers into chunks on paragraph breaks and translate each,
        # rather than silently truncating a long legal answer.
        max_chars = 4500
        if len(text) <= max_chars:
            return _translate_with_retry(text, "en", target_language_code)

        paragraphs = text.split("\n\n")
        translated_parts = []
        buffer = ""
        for para in paragraphs:
            if len(buffer) + len(para) + 2 <= max_chars:
                buffer = f"{buffer}\n\n{para}" if buffer else para
            else:
                translated_parts.append(_translate_with_retry(buffer, "en", target_language_code))
                buffer = para
        if buffer:
            translated_parts.append(_translate_with_retry(buffer, "en", target_language_code))
        return "\n\n".join(translated_parts)
    except TooManyRequests:
        print("[Translation warning] Rate-limited while translating the answer.")
        return text + "\n\n*(Translation service is temporarily rate-limited -- showing English.)*"
    except Exception as e:
        print(f"[Translation warning] Could not translate answer: {e}")
        return text + "\n\n*(Translation to your selected language failed -- showing English.)*"
