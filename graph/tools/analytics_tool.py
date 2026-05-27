"""
graph/tools/analytics_tool.py — YouTube Analytics Feedback Loop Tool
=====================================================================
Fetches recent channel metrics and generates performance hints using Gemini.
"""

import logging
from core.config_manager import config
from core.yt_analytics import is_connected, fetch_analytics

log = logging.getLogger("analytics_tool")

def get_performance_hint(profile_index: int = 0) -> str:
    """
    Connects to the YouTube Analytics system, fetches data from the last 28 days,
    and returns a summary of suggestions for the research agent.
    """
    if not is_connected(profile_index):
        log.info(f"YouTube Analytics is not connected for profile index {profile_index}.")
        return ""

    try:
        data = fetch_analytics(profile_index)
        if not data.get("ok"):
            log.warning(f"Failed to fetch YouTube analytics: {data.get('error')}")
            return ""

        views = data.get("views", 0)
        subs = data.get("subs", 0)
        earnings = data.get("earnings", 0.0)
        channel_name = data.get("channel_name", "Unknown Channel")
        total_subs = data.get("total_subs", 0)
        
        prompt = f"""
        Here is YouTube analytics data from the last 28 days:
        Channel Name: {channel_name}
        Total Views in last 28 days: {views} (Growth: {data.get('views_growth', 'N/A')})
        New Subscribers: {subs} (Growth: {data.get('subs_growth', 'N/A')})
        Total Subscriber Count: {total_subs}
        Estimated Revenue: ${earnings:.2f} (Growth: {data.get('earnings_growth', 'N/A')})

        In 2-3 sentences, summarize:
        - How the channel is performing.
        - What topics or strategies the creator should pursue to grow views and subscribers.
        - Give clear, actionable advice.

        Output ONLY the 2-3 sentence summary.
        """

        gemini_key = config.get("api_keys.gemini", "")
        if not gemini_key:
            return f"Channel '{channel_name}' has {views} views and {subs} new subscribers in the last 28 days."

        from langchain_google_genai import ChatGoogleGenerativeAI
        model_name = config.get("gemini_model") or config.get("pipeline.gemini_model") or "gemini-3.1-flash-lite"
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.7, google_api_key=gemini_key)
        response = llm.invoke(prompt)
        hint = response.content.strip()
        log.info(f"Generated performance hint: {hint}")
        return hint

    except Exception as exc:
        log.error(f"Error generating performance hint: {exc}", exc_info=True)
        return ""
