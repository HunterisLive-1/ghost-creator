"""Tests for script-provider LLM routing."""

from unittest.mock import MagicMock, patch

from graph.llm_factory import get_script_agent_llm, script_agent_provider_label


def test_script_agent_provider_label_defaults_to_gemini():
    with patch("graph.llm_factory.config") as mock_cfg:
        mock_cfg.get.return_value = ""
        assert script_agent_provider_label() == "gemini"


def test_get_script_agent_llm_uses_groq_when_selected():
    with patch("graph.llm_factory.config") as mock_cfg:
        def _get(key, default=None):
            data = {
                "script_provider": "groq",
                "groq_api_key": "gsk_test",
                "groq_model": "llama-3.3-70b-versatile",
            }
            return data.get(key, default)

        mock_cfg.get.side_effect = _get

        with patch("langchain_groq.ChatGroq") as mock_chat_groq:
            mock_chat_groq.return_value = MagicMock()
            llm = get_script_agent_llm(temperature=0.1)
            mock_chat_groq.assert_called_once_with(
                model="llama-3.3-70b-versatile",
                groq_api_key="gsk_test",
                temperature=0.1,
            )
            assert llm is mock_chat_groq.return_value
