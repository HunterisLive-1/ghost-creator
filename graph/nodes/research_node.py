"""
graph/nodes/research_node.py — Research Node
===========================================
Wraps modules/researcher.py with a LangChain Agent to discover trending topics.
"""

import json
import logging
from langchain_core.tools import Tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from core.config_manager import config
from graph.llm_factory import get_script_agent_llm, script_agent_provider_label
from graph.state import GhostCreatorState
from modules.researcher import find_trending_topic, get_tavily_api_key, RSS_FEEDS, _is_ai_tech

log = logging.getLogger("research_node")

def emit_progress(step: int, message: str, level: str = "INFO", run_id: str = ""):
    from api.routes.pipeline import get_broadcaster
    from datetime import datetime
    broadcaster = get_broadcaster()
    if broadcaster:
        broadcaster.put({
            "step": step,
            "message": message,
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
        })

def research_node(state: GhostCreatorState) -> dict:
    """LangGraph node to research a topic."""
    run_id = state.get("run_id", "")
    # 1. Skip research in custom script mode
    if state.get("mode") == "custom_script":
        return {
            "research_summary": "User-provided script mode. No research needed.",
            "trending_score": 1.0,
            "research_sources": [],
            "last_failed_node": ""
        }

    emit_progress(1, "🔍 Researching trending topic ...", "INFO", run_id)
    topic_hint = state.get("topic") or ""
    from graph.tools.analytics_tool import get_performance_hint
    past_performance_hint = get_performance_hint() or state.get("past_performance_hint") or "No prior data."

    # Emergency fallback function
    def emergency_fallback(exc_msg: str) -> dict:
        log.warning(f"Research node agent failed ({exc_msg}). Falling back to simple research.")
        fallback_topic = find_trending_topic()
        emit_progress(1, f"🔄 Research fallback → {fallback_topic}", "WARNING", run_id)
        # NOTE: Do NOT return 'errors' here — the fallback succeeded in finding a topic.
        # Returning errors would route the pipeline to error_recovery which aborts everything.
        return {
            "topic": fallback_topic,
            "research_summary": f"Trending topic discovered: {fallback_topic}.",
            "trending_score": 0.6,
            "research_sources": ["rss_fallback"],
            "past_performance_hint": past_performance_hint,
            "errors": [],          # Clear errors — fallback succeeded
            "last_failed_node": ""  # Not failed — we recovered successfully
        }

    try:
        provider = script_agent_provider_label()
        llm = get_script_agent_llm(temperature=0.7)
        log.info("Research agent using provider: %s", provider)

        # Build tools list
        tools = []
        tool_names: list[str] = []

        # 1. Tavily tool (if key available)
        tavily_key = get_tavily_api_key()
        if tavily_key:
            try:
                import os
                os.environ["TAVILY_API_KEY"] = tavily_key
                from langchain_tavily import TavilySearch
                tavily_tool = TavilySearch(
                    max_results=5,
                    name="tavily_search",
                    description=(
                        "Search the live web for trending AI/tech news. "
                        "Use this FIRST before other tools."
                    ),
                )
                tools.append(tavily_tool)
                tool_names.append("tavily_search")
                log.info("Tavily search enabled for research agent")
            except Exception as e:
                log.warning(f"Could not initialize Tavily Search Tool: {e}")
        else:
            log.warning(
                "Tavily API key not set — add it in Settings → API Keys to enable web search. "
                "Research will use Google Trends / RSS only."
            )

        # 2. Pytrends Search tool
        def run_pytrends(*args, **kwargs) -> str:
            try:
                return find_trending_topic()
            except Exception as e:
                return f"Error running pytrends: {e}"

        pytrends_tool = Tool(
            name="pytrends_search",
            func=run_pytrends,
            description="Fallback: check Google Trends for trending AI/tech search queries."
        )
        tools.append(pytrends_tool)
        tool_names.append("pytrends_search")

        # 3. RSS headlines tool
        def run_rss(*args, **kwargs) -> str:
            import feedparser
            import random
            headlines = []
            for url in RSS_FEEDS:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:10]:
                        title = entry.get("title", "")
                        if _is_ai_tech(title):
                            headlines.append(title)
                except Exception:
                    pass
            if not headlines:
                return "No recent AI headlines found in RSS feeds."
            random.shuffle(headlines)
            return "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines[:10]))

        rss_tool = Tool(
            name="rss_headlines",
            func=run_rss,
            description="Fallback: read TechCrunch, Wired, The Verge RSS feeds for AI/tech headlines."
        )
        tools.append(rss_tool)
        tool_names.append("rss_headlines")

        log.info("Research tools available: %s", ", ".join(tool_names) or "none")

        # System prompt setup
        topic_str = topic_hint if topic_hint.strip() else "latest trending AI news"
        system_prompt = (
            "You are a YouTube content research agent for Ghost Creator AI.\n"
            "Your goal: find the MOST viral, emotionally triggering AI/tech topic right now.\n\n"
            "Research strategy:\n"
            f"1. FIRST call tavily_search (if available) for live web results about \"{topic_str}\".\n"
            "2. If Tavily is unavailable, use pytrends_search for search spikes.\n"
            "3. Cross-check with rss_headlines.\n"
            f"4. Consider past performance: {past_performance_hint}\n\n"
            "Output a JSON with:\n"
            "{{\n"
            "  \"chosen_topic\": \"<one clear topic title>\",\n"
            "  \"research_summary\": \"<3 paragraphs: what it is, why it's viral, key facts>\",\n"
            "  \"trending_score\": <0.0 to 1.0>,\n"
            "  \"sources\": [\"<source1>\", \"<source2>\"]\n"
            "}}\n"
            "Respond ONLY with this JSON. No markdown fences, no ```json or ``` blocks."
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, max_iterations=4, verbose=False)

        # Run the agent
        response = executor.invoke({"input": "Find the trending topic and output the JSON."})
        # Parse agent output — newer LangChain versions can return a list instead of a string
        output = response.get("output", "")
        if isinstance(output, list):
            # Flatten list of message chunks to a single string
            output = " ".join(
                item.get("text", str(item)) if isinstance(item, dict) else str(item)
                for item in output
            )
        output = str(output).strip()

        # Parse JSON
        try:
            # Strip potential markdown code fences if LLM ignored instructions
            if output.startswith("```"):
                output = output.strip("`").replace("json\n", "", 1).strip()
            parsed = json.loads(output)
        except Exception as parse_exc:
            log.warning(f"Failed to parse research agent JSON response: {parse_exc}. Raw output: {output[:300]}")
            # Try to find JSON block in the output
            import re
            json_match = re.search(r"\{.*\}", output, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                except Exception:
                    raise parse_exc
            else:
                raise parse_exc

        return {
            "topic": parsed["chosen_topic"],
            "research_summary": parsed["research_summary"],
            "trending_score": float(parsed.get("trending_score", 0.5)),
            "research_sources": parsed.get("sources", []),
            "past_performance_hint": past_performance_hint,
            "last_failed_node": ""
        }

    except Exception as exc:
        return emergency_fallback(str(exc))
