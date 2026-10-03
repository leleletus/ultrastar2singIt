import os
import json

_translations = {}
_current_lang = "en"

def load_language(lang_code):
    global _translations, _current_lang
    _current_lang = lang_code
    if lang_code == "en":
        _translations = {}
        return
        
    locale_file = os.path.join(os.path.dirname(__file__), "locales", f"{lang_code}.json")
    if os.path.exists(locale_file):
        with open(locale_file, 'r', encoding='utf-8') as f:
            _translations = json.load(f)
    else:
        _translations = {}

def tr(text):
    return _translations.get(text, text)
