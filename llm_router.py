"""
Unified LLM router with automatic provider fallback between Google Gemini and Groq.
Eliminates dead endpoints and handles rate limits (429/503) gracefully.
"""
import os
import re
import json
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))

# Check API Keys
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

def is_google_available():
    return bool(GOOGLE_KEY and GOOGLE_KEY.strip())

def is_groq_available():
    return bool(GROQ_KEY and GROQ_KEY.strip())

def get_engine_options():
    options = []
    if is_google_available():
        options.append("⚡ Gemini 3.5 Flash Lite (500 RPD • 1.0s)")
        options.append("⚡ Gemini 2.5 Flash (Google AI)")
    if is_groq_available():
        options.append("🚀 Groq GPT-OSS 120B (14.4K RPD • Ultra Fast)")
    if is_google_available() and is_groq_available():
        options.insert(0, "🛡️ Auto-Failover (Gemini 3.5 Lite + Groq Hybrid)")
    if not options:
        options = ["No valid API keys detected in .env"]
    return options

def invoke_llm(prompt, preferred="auto", temperature=0.0, custom_keys=None):
    """
    Invokes the LLM with automatic fallback.
    Supports Bring Your Own Key (BYOK) via custom_keys dict.
    Returns (content_str, model_name_used).
    """
    google_key = (custom_keys.get("google") if custom_keys else None) or GOOGLE_KEY
    groq_key = (custom_keys.get("groq") if custom_keys else None) or GROQ_KEY
    claude_key = (custom_keys.get("anthropic") if custom_keys else None) or os.getenv("ANTHROPIC_API_KEY")

    models_to_try = []

    # If user provided a custom Anthropic key or requested Claude
    if claude_key and (preferred in ("claude", "anthropic") or "Claude" in preferred):
        models_to_try.append(("anthropic", "claude-3-5-sonnet-20241022"))
        models_to_try.append(("anthropic", "claude-3-5-haiku-20241022"))

    if preferred == "gemini" or "Gemini" in preferred:
        if google_key and str(google_key).strip():
            models_to_try.extend([
                ("gemini", "gemini-3.5-flash-lite"),
                ("gemini", "gemini-2.5-flash-lite"),
                ("gemini", "gemini-2.5-flash"),
            ])
        if groq_key and str(groq_key).strip():
            models_to_try.append(("groq", "openai/gpt-oss-120b"))
    elif preferred == "groq" or "Groq" in preferred:
        if groq_key and str(groq_key).strip():
            models_to_try.extend([
                ("groq", "openai/gpt-oss-120b"),
                ("groq", "openai/gpt-oss-20b"),
                ("groq", "qwen/qwen3.8-27b"),
            ])
        if google_key and str(google_key).strip():
            models_to_try.append(("gemini", "gemini-3.5-flash-lite"))
    else:  # auto / hybrid
        if google_key and str(google_key).strip():
            models_to_try.append(("gemini", "gemini-3.5-flash-lite"))
        if groq_key and str(groq_key).strip():
            models_to_try.append(("groq", "openai/gpt-oss-120b"))
        if claude_key and str(claude_key).strip():
            models_to_try.append(("anthropic", "claude-3-5-haiku-20241022"))
        if google_key and str(google_key).strip():
            models_to_try.append(("gemini", "gemini-2.5-flash-lite"))
            models_to_try.append(("gemini", "gemini-2.5-flash"))
        if groq_key and str(groq_key).strip():
            models_to_try.append(("groq", "openai/gpt-oss-20b"))

    last_error = None
    for provider, model_name in models_to_try:
        try:
            if provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(
                    model=model_name,
                    google_api_key=google_key,
                    temperature=temperature,
                    max_retries=1
                )
                res = llm.invoke(prompt)
                content = res.content
                if isinstance(content, list):
                    text_parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
                    content_str = "".join(text_parts).strip()
                else:
                    content_str = str(content).strip()
                return content_str, f"Gemini ({model_name})"
            elif provider == "groq":
                from langchain_groq import ChatGroq
                llm = ChatGroq(
                    model=model_name,
                    api_key=groq_key,
                    temperature=temperature,
                    max_retries=1
                )
                res = llm.invoke(prompt)
                content = res.content
                if isinstance(content, list):
                    text_parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
                    content_str = "".join(text_parts).strip()
                else:
                    content_str = str(content).strip()
                return content_str, f"Groq ({model_name})"
            elif provider == "anthropic":
                import requests
                headers = {
                    "x-api-key": claude_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "max_tokens": 2048,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                }
                resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                content_str = data["content"][0]["text"].strip()
                return content_str, f"Anthropic ({model_name})"
        except Exception as e:
            err_msg = str(e)
            print(f"[LLM Router] {provider} ({model_name}) failed: {err_msg[:120]} -> Trying fallback...")
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")


def parse_json_safely(raw_text):
    """
    Strips markdown code fences and extracts valid JSON dict or list.
    Handles surrounding chat text, markdown fences, and trailing commas.
    """
    if not raw_text or not str(raw_text).strip():
        raise ValueError("Empty response received from LLM")

    # 1. Look for markdown code fence first
    md_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE)
    candidate = md_match.group(1).strip() if md_match else raw_text.strip()

    try:
        return json.loads(candidate)
    except Exception:
        pass

    # 2. Extract largest enclosing {...}
    obj_match = re.search(r"\{[\s\S]*\}", candidate)
    if obj_match:
        try:
            clean_obj = re.sub(r",\s*([\}\]])", r"\1", obj_match.group(0))
            return json.loads(clean_obj)
        except Exception:
            pass

    # 3. Extract largest enclosing [...]
    arr_match = re.search(r"\[[\s\S]*\]", candidate)
    if arr_match:
        try:
            clean_arr = re.sub(r",\s*([\}\]])", r"\1", arr_match.group(0))
            return json.loads(clean_arr)
        except Exception:
            pass

    # 4. Fallback search on raw_text if candidate was trimmed
    obj_raw = re.search(r"\{[\s\S]*\}", raw_text)
    if obj_raw:
        try:
            clean_raw = re.sub(r",\s*([\}\]])", r"\1", obj_raw.group(0))
            return json.loads(clean_raw)
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON from LLM response: {raw_text[:200]}...")

