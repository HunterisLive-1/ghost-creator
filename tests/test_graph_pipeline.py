"""
tests/test_graph_pipeline.py — Smoke Test for LangGraph Pipeline
================================================================
Mocks external APIs (Gemini, Tavily, RSS, PyTrends, Image/Voice generation, SEO, assembly, uploader)
to verify the full LangGraph pipeline execution flow.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

# Set environment variable before importing pipeline to enable LangGraph mode
os.environ["GHOST_USE_LANGGRAPH"] = "1"

import pytest

@pytest.fixture
def mock_dependencies():
    """Fixture to patch all external network and heavy processing dependencies."""
    mock_backend = MagicMock()
    mock_backend.validate_config.return_value = (True, "")
    
    async def mock_generate(*args, **kwargs):
        return "temp_run_dir/img.png"
    mock_backend.generate = mock_generate

    def mock_asm_doc_side_effect(*args, **kwargs):
        from pathlib import Path
        output_dir = kwargs.get("output_dir") or args[3]
        output_filename = kwargs.get("output_filename") or args[4]
        return Path(output_dir) / output_filename

    def mock_assemble_side_effect(image_paths, audio_path, output_path, run_id=""):
        return output_path

    def mock_fetch_clips_side_effect(segments, output_dir, max_clip_duration=120, progress_callback=None):
        from pathlib import Path
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        clip_path = output_dir / "clip_01.mp4"
        clip_path.write_bytes(b"a" * 6000)
        return [str(clip_path)]

    mock_gen_script = MagicMock()
    mock_gen_doc_script = MagicMock()
    mock_gen_script.return_value = {
        "voiceover_text": "Welcome to the future of AI in 2026.",
        "image_prompts": ["futuristic AI robot", "code on screen"],
        "metadata": {
            "title": "AI in 2026",
            "description": "A video about AI.",
            "tags": ["AI"]
        }
    }
    mock_gen_doc_script.return_value = {
        "title": "AI in 2026",
        "voiceover_text": "Welcome to the future of AI in 2026.",
        "segments": [
            {"video_query": "futuristic robot", "voiceover": "Welcome to the future of AI in 2026."}
        ],
        "metadata": {
            "title": "AI in 2026",
            "description": "A documentary about AI.",
            "tags": ["AI"]
        }
    }

    def mock_trim_side_effect(src, dst, dur, vf):
        from pathlib import Path
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"a" * 6000)

    with patch("graph.llm_factory.get_script_agent_llm") as mock_agent_llm, \
         patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_gemini, \
         patch("graph.nodes.research_node.AgentExecutor") as mock_agent_executor, \
         patch("modules.researcher.find_trending_topic", return_value="AI in 2026") as mock_trends, \
         patch("graph.nodes.script_node.generate_script", mock_gen_script), \
         patch("graph.nodes.script_node.generate_documentary_script", mock_gen_doc_script), \
         patch("modules.video_fetcher.fetch_clips_for_pipeline", side_effect=mock_fetch_clips_side_effect) as mock_fetch_clips, \
         patch("modules.video_fetcher.footage_source_label", return_value="Stock") as mock_footage_label, \
         patch("core.clip_manager.load_clips") as mock_load_clips, \
         patch("modules.documentary_assembler.assemble_documentary", side_effect=mock_asm_doc_side_effect) as mock_asm_doc, \
         patch("modules.documentary_assembler._audio_duration_sec", return_value=10.0) as mock_aud_dur, \
         patch("modules.documentary_assembler._normalized_segment_durations", return_value=[10.0]) as mock_norm_dur, \
         patch("modules.documentary_assembler._trim_or_loop_clip", side_effect=mock_trim_side_effect) as mock_trim, \
         patch("modules.documentary_assembler._make_filler") as mock_filler, \
         patch("modules.voicer.run_voiceover", return_value="temp_run_dir/audio.mp3") as mock_voice, \
         patch("modules.image_gen._get_backend", return_value=mock_backend) as mock_image_backend, \
         patch("graph.nodes.assemble_node.compile_slideshow", side_effect=mock_assemble_side_effect) as mock_assemble, \
         patch("modules.uploader.upload_to_youtube") as mock_upload, \
         patch("graph.tools.analytics_tool.is_connected", return_value=False) as mock_analytics_connected, \
         patch("pathlib.Path.exists", return_value=True):

        # Configure AgentExecutor mock
        mock_executor_instance = MagicMock()
        mock_executor_instance.invoke.return_value = {
            "output": '{\n  "chosen_topic": "AI in 2026",\n  "research_summary": "Welcome to the future of AI in 2026.",\n  "trending_score": 0.8,\n  "sources": ["mock_source"]\n}'
        }
        mock_agent_executor.return_value = mock_executor_instance

        # Configure structured output mock for Script Critic
        critic_instance = MagicMock()
        critic_instance.invoke.return_value = MagicMock(
            overall_score=8.5,
            hook_score=8.0,
            retention_score=8.0,
            emotion_score=8.0,
            clarity_score=8.0,
            tts_friendliness=8.0,
            strengths=["good hook"],
            weaknesses=["none"],
            rewrite_suggestion="none",
            verdict="excellent"
        )
        
        # Configure structured output mock for SEO Agent
        seo_instance = MagicMock()
        seo_instance.invoke.return_value = MagicMock(
            title="Optimized Title",
            description="Optimized Description",
            tags=["tag1", "tag2"],
            hashtags=["#tag"],
            chapters=[]
        )

        # Configure Gemini mock behaviour
        llm_instance = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = '{\n  "chosen_topic": "AI in 2026",\n  "research_summary": "Welcome to the future of AI in 2026.",\n  "trending_score": 0.8,\n  "sources": ["mock_source"]\n}'
        llm_instance.invoke.return_value = mock_msg
        
        def with_structured_output_mock(schema):
            from graph.nodes.script_critic_node import CriticOutput
            from graph.nodes.seo_node import SEOOutput
            if schema == CriticOutput:
                return critic_instance
            if schema == SEOOutput:
                return seo_instance
            return llm_instance

        llm_instance.with_structured_output.side_effect = with_structured_output_mock
        mock_gemini.return_value = llm_instance
        mock_agent_llm.return_value = llm_instance

        # Configure ClipInfo loading
        from core.clip_manager import ClipInfo
        from pathlib import Path
        mock_load_clips.return_value = [
            ClipInfo(
                path=Path("temp_run_dir/clips/clip_01.mp4"),
                duration=10.0,
                search_query="futuristic robot",
                segment_index=0,
                target_duration_sec=10.0
            )
        ]

        yield {
            "gemini": mock_gemini,
            "trends": mock_trends,
            "gen_script": mock_gen_script,
            "gen_doc_script": mock_gen_doc_script,
            "fetch_clips": mock_fetch_clips,
            "voice": mock_voice,
            "image_backend": mock_image_backend,
            "assemble": mock_assemble,
            "asm_doc": mock_asm_doc,
            "upload": mock_upload
        }

def test_full_pipeline_flow(mock_dependencies, tmp_path):
    """Verifies shorts mode with stock footage uses video clips, not Gemini images."""
    from graph.pipeline import build_pipeline
    from graph.state import default_state
    
    # 1. Build pipeline with InMemorySaver checkpointer
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = build_pipeline(checkpointer=checkpointer)

    # 2. Setup mock state
    initial_state = default_state()
    initial_state.update({
        "mode": "shorts",
        "topic": "AI in 2026",
        "run_id": "test_001",
        "run_dir": str(tmp_path),
        "max_script_attempts": 1,
        "script_auto_approved": True,  # Mocks the human review interrupt to auto-approve
        "review_decision": "approved"  # Prevent pausing on human_review
    })

    # 3. Configure mock config file
    from core.config_manager import config
    config.set("api_keys.gemini", "mock-gemini-key")
    config.set("documentary.footage_source", "stock")
    config.set("pipeline.upload_enabled", False)  # Skip upload step
    config.set("pipeline.skip_human_review", True)
    config.set("pipeline.auto_approve_threshold", 7.0)

    # 4. Invoke graph (will pause before human_review)
    config_dict = {"configurable": {"thread_id": "test_run_123"}}
    graph.invoke(initial_state, config=config_dict)
    
    # Resume from the interrupt point by checking the state snapshot
    state_snapshot = graph.get_state(config_dict)
    if "human_review" in state_snapshot.next:
        final_state = graph.invoke(None, config=config_dict)
    else:
        final_state = state_snapshot.values

    # 5. Asserts — stock footage path for shorts
    assert final_state["script"] is not None
    assert final_state["script"]["voiceover_text"] == "Welcome to the future of AI in 2026."
    assert "segments" in final_state["script"]
    assert final_state["script_quality_score"] == 8.5
    assert final_state["review_decision"] == "approved"
    assert final_state["seo_optimized"] is True
    assert final_state["video_path"].startswith(str(tmp_path))
    assert len(final_state["image_paths"]) == 0
    mock_dependencies["gen_doc_script"].assert_called()
    mock_dependencies["gen_script"].assert_not_called()
    mock_dependencies["fetch_clips"].assert_called()
    mock_dependencies["assemble"].assert_not_called()
    mock_dependencies["asm_doc"].assert_called()


def test_shorts_ai_images_slideshow(mock_dependencies, tmp_path):
    """Verifies AI Images footage source still uses Gemini slideshow path for shorts."""
    from graph.pipeline import build_pipeline
    from graph.state import default_state
    from langgraph.checkpoint.memory import InMemorySaver

    graph = build_pipeline(checkpointer=InMemorySaver())

    initial_state = default_state()
    initial_state.update({
        "mode": "shorts",
        "topic": "AI in 2026",
        "run_id": "test_003",
        "run_dir": str(tmp_path),
        "max_script_attempts": 1,
        "script_auto_approved": True,
        "review_decision": "approved",
    })

    from core.config_manager import config
    config.set("api_keys.gemini", "mock-gemini-key")
    config.set("documentary.footage_source", "ai_images")
    config.set("pipeline.upload_enabled", False)
    config.set("pipeline.skip_human_review", True)
    config.set("pipeline.auto_approve_threshold", 7.0)

    config_dict = {"configurable": {"thread_id": "test_run_789"}}
    graph.invoke(initial_state, config=config_dict)
    state_snapshot = graph.get_state(config_dict)
    if "human_review" in state_snapshot.next:
        final_state = graph.invoke(None, config=config_dict)
    else:
        final_state = state_snapshot.values

    assert final_state["video_path"].startswith(str(tmp_path))
    mock_dependencies["gen_script"].assert_called()
    mock_dependencies["gen_doc_script"].assert_not_called()
    mock_dependencies["assemble"].assert_called()
    mock_dependencies["fetch_clips"].assert_not_called()


def test_documentary_pipeline_flow(mock_dependencies, tmp_path):
    """Verifies that documentary mode pipeline runs completely, bypassing image generation."""
    from graph.pipeline import build_pipeline
    from graph.state import default_state
    
    # 1. Build pipeline with InMemorySaver checkpointer
    from langgraph.checkpoint.memory import InMemorySaver
    checkpointer = InMemorySaver()
    graph = build_pipeline(checkpointer=checkpointer)

    # 2. Setup mock state
    initial_state = default_state()
    initial_state.update({
        "mode": "documentary",
        "topic": "AI in 2026",
        "run_id": "test_002",
        "run_dir": str(tmp_path),
        "max_script_attempts": 1,
        "script_auto_approved": True,  # Mocks the human review interrupt to auto-approve
        "review_decision": "approved"  # Prevent pausing on human_review
    })

    # 3. Configure mock config file
    from core.config_manager import config
    config.set("api_keys.gemini", "mock-gemini-key")
    config.set("documentary.footage_source", "stock")
    config.set("pipeline.upload_enabled", False)  # Skip upload step
    config.set("pipeline.skip_human_review", True)
    config.set("pipeline.auto_approve_threshold", 7.0)

    # 4. Invoke graph
    config_dict = {"configurable": {"thread_id": "test_run_456"}}
    graph.invoke(initial_state, config=config_dict)
    
    # Resume from the interrupt point by checking the state snapshot
    state_snapshot = graph.get_state(config_dict)
    if "human_review" in state_snapshot.next:
        final_state = graph.invoke(None, config=config_dict)
    else:
        final_state = state_snapshot.values

    # 5. Asserts
    assert final_state["script"] is not None
    assert final_state["script"]["voiceover_text"] == "Welcome to the future of AI in 2026."
    assert len(final_state["image_paths"]) == 0  # Assert images are bypassed
    assert final_state["video_path"].startswith(str(tmp_path))
