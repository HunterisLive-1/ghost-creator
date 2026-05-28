"""Resolve LangChain chat models from Settings → script_provider."""

from __future__ import annotations

from core.config_manager import config


def get_script_agent_llm(*, temperature: float = 0.2):
    """
    Return a LangChain chat model for agent nodes (critic, SEO, etc.)
    using the same provider selected for script writing.
    """
    provider = (config.get("script_provider") or "gemini").lower().strip()

    if provider == "groq":
        from langchain_groq import ChatGroq

        api_key = (config.get("groq_api_key") or "").strip()
        if not api_key:
            raise ValueError(
                "Groq API key is not set. Add it in Settings → AI Script Provider."
            )
        model = config.get("groq_model") or "llama-3.3-70b-versatile"
        return ChatGroq(model=model, groq_api_key=api_key, temperature=temperature)

    if provider == "ollama":
        from langchain_community.chat_models import ChatOllama

        base_url = (config.get("ollama_url") or "http://localhost:11434").rstrip("/")
        model = config.get("ollama_model") or "llama3"
        return ChatOllama(base_url=base_url, model=model, temperature=temperature)

    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = (config.get("api_keys.gemini") or "").strip()
    if not api_key:
        raise ValueError("Missing Gemini API key in configuration.")
    model = (
        config.get("gemini_model")
        or config.get("pipeline.gemini_model")
        or "gemini-3.1-flash-lite"
    )
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
    )


def script_agent_provider_label() -> str:
    return (config.get("script_provider") or "gemini").lower().strip()
