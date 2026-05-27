# CURSOR_PROMPTS.md — Ghost Creator AI v5 (LangGraph + LangChain Agentic Upgrade)

> **Target:** Upgrade Ghost Creator AI from a sequential threaded pipeline to a
> fully agentic, stateful, self-recovering LangGraph workflow.
>
> **Work style:** Each Phase is a standalone Cursor prompt. Run them one at a time.
> Complete Phase N fully before starting Phase N+1.
>
> **Repo root:** `ghost-creator-main/`

---

## 📦 PRE-REQUISITE — Install Dependencies First

Before running any prompt, install the new dependencies:

```bash
pip install langgraph langchain langchain-google-genai langchain-community \
            langgraph-checkpoint-sqlite tavily-python langchain-core \
            pydantic>=2.0 aiosqlite
```

Add these to `requirements.txt` as well.

---

---

# PHASE 1 — LangGraph State Schema + Folder Structure

## Cursor Prompt 1.1 — Create the `graph/` package

```
Create the following new folder structure inside the project root (ghost-creator-main/):

graph/
├── __init__.py
├── state.py
├── pipeline.py
├── nodes/
│   ├── __init__.py
│   ├── research_node.py
│   ├── script_node.py
│   ├── script_critic_node.py
│   ├── human_review_node.py
│   ├── image_node.py
│   ├── voiceover_node.py
│   ├── seo_node.py
│   ├── assemble_node.py
│   └── upload_node.py
└── tools/
    ├── __init__.py
    ├── web_search_tool.py
    └── analytics_tool.py

Do NOT delete or modify any existing file. Only create new files.
Create all files as empty stubs with a one-line docstring for now.
We will fill them phase by phase.
```

---

## Cursor Prompt 1.2 — Define the Central State

```
File to create: graph/state.py

Implement the LangGraph TypedDict state for Ghost Creator AI v5.
This state flows through every node in the graph.

Requirements:
1. Import: TypedDict, Annotated, Literal from typing; operator; add_messages from langgraph.graph.message
2. Define a `PipelineMode` Literal type: "shorts" | "documentary" | "custom_script"
   - "shorts"         = AI picks topic + writes script + generates images (original flow)
   - "documentary"    = AI picks topic + writes long-form script + downloads YouTube footage
   - "custom_script"  = User provides their OWN script text; AI only polishes + generates media

3. Define `GhostCreatorState(TypedDict)` with these fields:

   # ── Input ──────────────────────────────────────────────────────
   mode: PipelineMode
   topic: str                          # user-provided or auto-discovered
   user_custom_script: str             # NEW: raw text the user typed themselves (empty if mode != "custom_script")
   language: str                       # "hi" / "hinglish" / "en" etc.
   run_id: str
   run_dir: str                        # absolute path to per-run output folder

   # ── Research ───────────────────────────────────────────────────
   research_summary: str               # multi-source research paragraph
   trending_score: float               # 0.0–1.0 virality estimate
   research_sources: list[str]         # URLs / feed names used

   # ── Script ─────────────────────────────────────────────────────
   script: dict                        # {"voiceover_text", "image_prompts", "metadata": {title, description, tags}}
   script_version: int                 # increments on each regeneration
   script_attempts: int                # total generation attempts
   max_script_attempts: int            # configurable limit (default 3)

   # ── Script Quality ─────────────────────────────────────────────
   script_quality_score: float         # 0.0–10.0 from script_critic_node
   script_quality_feedback: str        # critic's detailed feedback
   script_auto_approved: bool          # True if score >= threshold and skip_review=True

   # ── Human Review ───────────────────────────────────────────────
   review_decision: Literal["approved", "rejected", "pending"]
   review_feedback: str                # user typed feedback when rejecting

   # ── Parallel Generation ────────────────────────────────────────
   image_paths: Annotated[list[str], operator.add]   # parallel workers append here
   audio_path: str
   thumbnail_path: str

   # ── SEO ────────────────────────────────────────────────────────
   seo_title: str
   seo_description: str
   seo_tags: list[str]
   seo_optimized: bool

   # ── Assembly & Upload ──────────────────────────────────────────
   video_path: str
   upload_status: dict                 # {"ok", "url", "video_id", "error"}

   # ── Agentic Error Recovery ─────────────────────────────────────
   errors: Annotated[list[str], operator.add]
   retry_counts: dict[str, int]        # node_name → retry count
   last_failed_node: str

   # ── Analytics Feedback (from previous runs) ────────────────────
   past_performance_hint: str          # summary injected from yt_analytics

4. Add a factory function `default_state() -> GhostCreatorState` that returns
   a state dict with all sensible defaults (empty strings, empty lists, 0s, "pending", etc.)

5. Add a helper `merge_state(base: dict, updates: dict) -> dict` that shallow-merges
   two state dicts (used by nodes to return partial updates cleanly).
```

---

---

# PHASE 2 — Research Agent Node

## Cursor Prompt 2.1 — Research Node with LangChain Agent

```
File to create: graph/nodes/research_node.py

Context:
- Existing file: modules/researcher.py — has find_trending_topic() using pytrends + RSS feeds
- We are NOT deleting researcher.py. The new node wraps + supercharges it.
- State field this node reads: state["topic"], state["mode"], state["past_performance_hint"]
- State fields this node writes: research_summary, trending_score, research_sources, topic (if empty)

Implement `research_node(state: GhostCreatorState) -> dict`:

1. If state["mode"] == "custom_script":
   - Skip all research. The user wrote their own script.
   - Return: {"research_summary": "User-provided script mode. No research needed.", "trending_score": 1.0, "research_sources": []}

2. Otherwise, build a LangChain agent:
   a. LLM: ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7)
      Get the Gemini API key from: core/config_manager.config.get("api_keys.gemini", "")
      
   b. Tools list:
      - TavilySearchResults(max_results=5, api_key=config.get("api_keys.tavily", ""))
        Wrap this in a try/except — if Tavily key is missing, skip this tool silently.
      - A custom LangChain Tool called "pytrends_search" that calls
        modules.researcher.find_trending_topic() and returns the result as a string.
      - A custom LangChain Tool called "rss_headlines" that parses the RSS_FEEDS
        list from modules.researcher and returns top 10 AI/tech headlines as a
        numbered string list.

   c. System prompt for the agent:
      """
      You are a YouTube content research agent for Ghost Creator AI.
      Your goal: find the MOST viral, emotionally triggering AI/tech topic right now.

      Research strategy:
      1. Search for the topic "{topic_hint}" if provided, otherwise find trending AI news.
      2. Check pytrends for real-time search spikes.
      3. Cross-reference with RSS headlines.
      4. Consider past performance: {past_performance_hint}

      Output a JSON with:
      {{
        "chosen_topic": "<one clear topic title>",
        "research_summary": "<3 paragraphs: what it is, why it's viral, key facts>",
        "trending_score": <0.0 to 1.0>,
        "sources": ["<source1>", "<source2>"]
      }}
      Respond ONLY with this JSON. No markdown fences.
      """
      Replace {topic_hint} with state["topic"] or "latest trending AI news".
      Replace {past_performance_hint} with state["past_performance_hint"] or "No prior data."

   d. Run the agent with AgentExecutor(agent=..., tools=..., max_iterations=4, verbose=False)

   e. Parse the JSON output. If JSON parse fails, fall back to calling
      modules.researcher.find_trending_topic() directly and building a minimal dict.

3. Return:
   {
     "topic": parsed["chosen_topic"],
     "research_summary": parsed["research_summary"],
     "trending_score": parsed.get("trending_score", 0.5),
     "research_sources": parsed.get("sources", [])
   }

4. Wrap the entire function in try/except. On any exception:
   - Call modules.researcher.find_trending_topic() as emergency fallback
   - Return minimal valid state dict
   - Append error to state["errors"] via {"errors": [str(exc)]}
```

---

---

# PHASE 3 — Script Writer Node (Structured Output)

## Cursor Prompt 3.1 — Script Node with Pydantic Structured Output

```
File to create: graph/nodes/script_node.py

Context:
- Existing file: modules/scripter.py — has generate_script() and generate_documentary_script()
- We are NOT deleting scripter.py. The new node adds structured output + custom script support.
- This node handles BOTH AI-written scripts AND user custom scripts.

Step A — Define Pydantic models at the top of the file:

  class ImagePromptItem(BaseModel):
      prompt: str = Field(description="Cinematic English image prompt for Stable Diffusion / Imagen")
      scene_index: int = Field(description="Scene number starting from 0")

  class VideoMetadata(BaseModel):
      title: str = Field(description="YouTube video title, max 100 chars, click-bait but accurate")
      description: str = Field(description="YouTube description, 150-300 words, SEO rich")
      tags: list[str] = Field(description="10-15 YouTube tags")

  class GeneratedScript(BaseModel):
      voiceover_text: str = Field(description="Full TTS-ready narration, no markdown, plain spoken sentences")
      image_prompts: list[ImagePromptItem] = Field(description="5-6 cinematic scene prompts in English")
      metadata: VideoMetadata

Step B — Implement `script_node(state: GhostCreatorState) -> dict`:

  MODE BRANCHING:

  --- BRANCH A: mode == "custom_script" ---
  The user has written their own script. Our job is to POLISH it, not replace it.

  1. Read state["user_custom_script"] — this is the user's raw text.
  2. If it's empty or < 50 chars, emit an error and fall back to AI writing mode.
  3. Build a polish prompt:
     """
     You are a professional YouTube script editor.
     The user has written their own script. Polish it:
     - Fix grammar, flow, and pacing for spoken narration
     - Ensure the first sentence is a strong hook (question or shocking fact)
     - Add natural spoken transitions ("Ab baat karte hain...", "Lekin yahan twist hai...")
     - Language: {language_instruction}
     - Do NOT change the core message or facts — only improve delivery
     - Keep it TTS-friendly: no symbols, emojis, bullets, markdown
     - Generate 5-6 cinematic image prompts in English that match the script's scenes
     - Generate an optimized YouTube title, description, and tags

     User's original script:
     ---
     {user_custom_script}
     ---
     """
  4. Use llm.with_structured_output(GeneratedScript) to get a clean polished result.
  5. Set a note in the returned state: script["_source"] = "user_custom_polished"

  --- BRANCH B: mode == "shorts" or "documentary" ---
  Full AI script generation.

  1. Call modules.scripter.generate_script() or generate_documentary_script()
     with the existing config (preserve all existing logic for compatibility).
  2. Convert the returned dict into a GeneratedScript-shaped dict.
  3. Set script["_source"] = "ai_generated"

  RETURN (both branches):
  {
    "script": script_dict,          # GeneratedScript as dict
    "script_version": state.get("script_version", 0) + 1,
    "script_attempts": state.get("script_attempts", 0) + 1,
  }

  On exception: append to errors, return {"errors": [str(exc)], "script": {}}
```

---

---

# PHASE 4 — Script Critic Agent (NEW Agentic Node)

## Cursor Prompt 4.1 — Autonomous Script Quality Evaluator

```
File to create: graph/nodes/script_critic_node.py

This is a NEW node that does NOT exist in the current codebase.
It acts as an autonomous AI reviewer that scores the script BEFORE showing it to the human.
If the score is high enough, the pipeline can skip human review entirely (auto-approve mode).

Implement `script_critic_node(state: GhostCreatorState) -> dict`:

1. If state["script"] is empty or has no voiceover_text, return immediately:
   {"script_quality_score": 0.0, "script_quality_feedback": "Empty script", "script_auto_approved": False}

2. Build a Pydantic model for the critic's output:

   class CriticOutput(BaseModel):
       hook_score: float = Field(ge=0, le=10, description="First 3 seconds hook strength")
       retention_score: float = Field(ge=0, le=10, description="Will viewers watch till end?")
       emotion_score: float = Field(ge=0, le=10, description="Emotional impact / surprise / curiosity")
       clarity_score: float = Field(ge=0, le=10, description="Are the facts clear and accurate?")
       tts_friendliness: float = Field(ge=0, le=10, description="Is it good for TTS? No symbols, good pacing?")
       overall_score: float = Field(ge=0, le=10, description="Weighted average")
       strengths: list[str] = Field(description="Top 3 things done well")
       weaknesses: list[str] = Field(description="Top 3 things to improve")
       rewrite_suggestion: str = Field(description="One specific rewrite for the opening hook if needed")
       verdict: Literal["excellent", "good", "needs_work", "reject"]

3. Critic prompt:
   """
   You are a ruthless YouTube Shorts script critic with 10 years of viral content experience.
   Evaluate this script as if your job depends on it getting 100K+ views.

   Script language: {language}
   Script source: {script_source}  (ai_generated or user_custom_polished)
   Topic: {topic}

   SCRIPT:
   ---
   {voiceover_text}
   ---

   Score each dimension from 0-10. Be harsh. A 7 is average.
   Viral shorts need hook_score >= 8, emotion_score >= 7.
   """

4. Run: llm.with_structured_output(CriticOutput).invoke(critic_prompt)

5. Auto-approval logic:
   - Read config: auto_approve_threshold = config.get("pipeline.auto_approve_threshold", 8.0)
   - Read config: skip_human_review = config.get("pipeline.skip_human_review", False)
   - auto_approved = skip_human_review AND critic.overall_score >= auto_approve_threshold

6. Return:
   {
     "script_quality_score": critic.overall_score,
     "script_quality_feedback": json.dumps({
         "scores": {...}, "strengths": ..., "weaknesses": ..., "rewrite_suggestion": ...
     }),
     "script_auto_approved": auto_approved,
     "review_decision": "approved" if auto_approved else "pending"
   }

7. Also log a colourful summary using the existing config.get_logger("critic") system.
```

---

---

# PHASE 5 — Human Review Node (LangGraph interrupt)

## Cursor Prompt 5.1 — Replace threading.Event with LangGraph interrupt()

```
File to create: graph/nodes/human_review_node.py

Context:
- CURRENT approach in pipeline_runner.py: uses threading.Event and polling
  (self._script_review_event, self.pending_script_data, self.waiting_for_script_review)
- NEW approach: LangGraph's native interrupt() — graph execution SUSPENDS here
  and resumes when the API receives the user's decision.

Implement `human_review_node(state: GhostCreatorState) -> dict`:

1. If state["review_decision"] == "approved" or state["script_auto_approved"] == True:
   - Skip — already approved (either by critic or previous iteration)
   - Return {"review_decision": "approved"}

2. Otherwise, call LangGraph interrupt():

   from langgraph.types import interrupt

   user_decision = interrupt({
     "event": "script_review_required",
     "run_id": state["run_id"],
     "script": state["script"],
     "quality_score": state["script_quality_score"],
     "quality_feedback": json.loads(state.get("script_quality_feedback", "{}")),
     "script_version": state["script_version"],
     "script_attempts": state["script_attempts"],
     "max_attempts": state["max_script_attempts"],
     "message": "Script ready for your review. Approve, reject with feedback, or edit directly."
   })

   # user_decision comes back from the API when user submits their choice
   # Expected shape: {"action": "approved"|"rejected"|"edited", "feedback": str, "edited_script": dict|None}

3. Handle the response:
   if user_decision["action"] == "approved":
       return {"review_decision": "approved", "review_feedback": ""}

   elif user_decision["action"] == "edited":
       # User edited the script directly in the UI
       edited = user_decision.get("edited_script", {})
       new_script = {**state["script"], **edited}
       return {"review_decision": "approved", "script": new_script, "review_feedback": "User edited directly"}

   elif user_decision["action"] == "rejected":
       return {
         "review_decision": "rejected",
         "review_feedback": user_decision.get("feedback", "No feedback provided")
       }

4. Add a `route_after_review(state) -> str` function:
   - If "approved" → return "parallel_generation"
   - If "rejected" AND attempts < max_attempts → return "script_node"
   - If "rejected" AND attempts >= max_attempts → return END  (stop pipeline)
   This function will be used as a conditional edge in pipeline.py.
```

---

---

# PHASE 6 — Parallel Image + Voice Generation

## Cursor Prompt 6.1 — Parallel Worker Nodes with LangGraph Send()

```
File to create: graph/nodes/image_node.py

Context:
- Existing: modules/image_gen.py — has image generation logic
- Existing: backends/image/gemini_imagen.py — Gemini Imagen backend

Implement TWO things in this file:

A) `spawn_parallel_tasks(state: GhostCreatorState) -> list`:
   """
   Fan-out node: spawns one image worker per image prompt + one voiceover worker.
   Returns a list of Send() objects for LangGraph parallel execution.
   """
   from langgraph.types import Send
   sends = []
   image_prompts = state["script"].get("image_prompts", [])
   for i, prompt_item in enumerate(image_prompts):
       prompt_str = prompt_item if isinstance(prompt_item, str) else prompt_item.get("prompt", "")
       sends.append(Send("image_worker", {
           "image_prompt": prompt_str,
           "scene_index": i,
           "run_dir": state["run_dir"],
           "run_id": state["run_id"],
       }))
   # Voiceover runs in parallel with images
   sends.append(Send("voiceover_worker", {
       "voiceover_text": state["script"].get("voiceover_text", ""),
       "language": state["language"],
       "run_dir": state["run_dir"],
   }))
   return sends

B) `image_worker_node(worker_state: dict) -> dict`:
   """
   Single image generation worker. Called once per image prompt in parallel.
   """
   1. Call existing modules.image_gen logic (or backends.image.gemini_imagen directly)
      to generate one image from worker_state["image_prompt"].
   2. Save the image to: {run_dir}/image_{scene_index:02d}.png
   3. On success return: {"image_paths": [str(saved_path)]}
      (Annotated list in state — each worker APPENDS, they don't overwrite)
   4. On failure return: {"image_paths": [], "errors": [f"Image {scene_index} failed: {exc}"]}
   5. Implement retry: max 2 retries with 3-second sleep between attempts.
      Track via: worker_state.get("retry_counts", {}).get("image_worker", 0)
```

---

## Cursor Prompt 6.2 — Voiceover Worker Node

```
File to create: graph/nodes/voiceover_node.py

Context:
- Existing: modules/voicer.py — has run_voiceover()
- This node runs IN PARALLEL with image_worker nodes via LangGraph Send()

Implement `voiceover_worker_node(worker_state: dict) -> dict`:

1. Call modules.voicer.run_voiceover() with:
   - text = worker_state["voiceover_text"]
   - output_dir = worker_state["run_dir"]
   - language = worker_state["language"]
   - Pass through all existing TTS backend config from core.config_manager.config

2. The run_voiceover function returns an audio file path (str).
3. Return: {"audio_path": audio_path}
4. On failure: {"audio_path": "", "errors": [f"Voiceover failed: {exc}"]}
5. Implement 2 retries with 5-second sleep.

NOTE: Both image workers and this voiceover worker write to different state keys
(image_paths vs audio_path) so there are NO write conflicts even in parallel.
```

---

---

# PHASE 7 — SEO Optimization Agent (NEW)

## Cursor Prompt 7.1 — SEO Agent Node

```
File to create: graph/nodes/seo_node.py

This is a NEW autonomous agent node that does NOT exist in the current codebase.
It rewrites and optimizes title, description, and tags AFTER script approval,
using real YouTube SEO best practices.

Implement `seo_node(state: GhostCreatorState) -> dict`:

Step 1 — Build a Pydantic model:

  class SEOOutput(BaseModel):
      title: str = Field(description="YouTube title: max 60 chars, front-load keywords, power word first")
      description: str = Field(description="YouTube description: keyword-rich, 150-250 words, natural language")
      tags: list[str] = Field(description="Exactly 15 tags: mix of broad + niche + long-tail")
      hashtags: list[str] = Field(description="5 hashtags for the video description footer")
      chapters: list[str] = Field(description="YouTube chapter timestamps if script has natural sections, else empty list")

Step 2 — Prompt:
  """
  You are a YouTube SEO specialist. Optimize this video's metadata to maximize
  impressions and click-through rate.

  Topic: {topic}
  Script (first 400 chars for context): {voiceover_preview}
  Current title: {current_title}
  Current tags: {current_tags}
  Language of voiceover: {language}

  SEO Rules:
  - Title: Put the most searched keyword in the FIRST 3 words. Use numbers or "?" if natural.
    Examples of power openers: "यह क्या है?", "2025 में...", "जो कोई नहीं बताता..."
  - Tags: Start with exact-match tags, then broader category tags, then question tags.
  - Description: First 2 lines must be compelling (shown before "Show more").
    Include a soft CTA: "Subscribe karo aur bell icon dabao!"
  - All metadata in language: {language}
  - Hashtags go at the very END of the description.
  """

Step 3 — Run llm.with_structured_output(SEOOutput).invoke(seo_prompt)

Step 4 — Return:
  {
    "seo_title": result.title,
    "seo_description": result.description + "\n\n" + " ".join(result.hashtags),
    "seo_tags": result.tags,
    "seo_optimized": True,
    # Also update the script's metadata so assembly uses the optimized version
    "script": {**state["script"], "metadata": {
        "title": result.title,
        "description": result.description,
        "tags": result.tags
    }}
  }

Step 5 — If Gemini call fails, return the original script metadata unchanged with seo_optimized=False.
```

---

---

# PHASE 8 — Assembly + Upload Nodes (Wrappers)

## Cursor Prompt 8.1 — Assembly Node

```
File to create: graph/nodes/assemble_node.py

Context:
- Existing: modules/documentary_assembler.py — has assemble_documentary()
- This node is a clean LangGraph wrapper around the existing assembler.
- It runs AFTER all parallel image + voice workers complete (join point).

Implement `assemble_node(state: GhostCreatorState) -> dict`:

1. Validate prerequisites:
   - state["audio_path"] must be non-empty. If empty, raise and return error.
   - state["image_paths"] must have at least 1 path. If empty, raise and return error.
   - All paths must exist on disk (use Path(p).exists() check).

2. Call the existing assembly logic. For "documentary" mode:
   from modules.documentary_assembler import assemble_documentary
   video_path = assemble_documentary(...)  # pass existing params from state + config

   For "shorts" or "custom_script" mode:
   Use the existing non-documentary assembly logic from pipeline_runner.py
   (the _run() method's assembly section — port it here cleanly).

3. On success: return {"video_path": str(video_path)}
4. On failure: return {"video_path": "", "errors": [f"Assembly failed: {exc}"], "last_failed_node": "assemble"}
5. Add a progress callback that emits to the existing ProgressBroadcaster system
   (import from api.services.progress_broadcaster).
```

---

## Cursor Prompt 8.2 — Upload Node

```
File to create: graph/nodes/upload_node.py

Context:
- Existing: modules/uploader.py — has upload_to_youtube()
- Existing: core/config_manager.config — has "pipeline.upload_enabled"

Implement `upload_node(state: GhostCreatorState) -> dict`:

1. Check: if not config.get("pipeline.upload_enabled", True):
   return {"upload_status": {"ok": True, "skipped": True, "reason": "Upload disabled in settings"}}

2. Check: if not state["video_path"] or not Path(state["video_path"]).exists():
   return {"upload_status": {"ok": False, "error": "No video file to upload"}}

3. Call modules.uploader.upload_to_youtube() with:
   - video_path = state["video_path"]
   - title = state["seo_title"] or state["script"]["metadata"]["title"]
   - description = state["seo_description"] or state["script"]["metadata"]["description"]
   - tags = state["seo_tags"] or state["script"]["metadata"]["tags"]
   - thumbnail = state.get("thumbnail_path", "")
   - progress_callback = (lambda msg: broadcaster.broadcast_sync({"message": msg}))

4. On success: return {"upload_status": {"ok": True, "url": result_url, "video_id": video_id}}
5. On failure: return {"upload_status": {"ok": False, "error": str(exc)}}
```

---

---

# PHASE 9 — Main Pipeline Graph Assembly

## Cursor Prompt 9.1 — Build and Compile the LangGraph Pipeline

```
File to create: graph/pipeline.py

This is the central file that wires ALL nodes into a compiled LangGraph graph.
This REPLACES core/pipeline_runner.py's threading logic.

Requirements:

1. Imports:
   from langgraph.graph import StateGraph, START, END
   from langgraph.checkpoint.sqlite import SqliteSaver
   from langgraph.types import Send
   from graph.state import GhostCreatorState
   from graph.nodes.research_node import research_node
   from graph.nodes.script_node import script_node
   from graph.nodes.script_critic_node import script_critic_node
   from graph.nodes.human_review_node import human_review_node, route_after_review
   from graph.nodes.image_node import spawn_parallel_tasks, image_worker_node
   from graph.nodes.voiceover_node import voiceover_worker_node
   from graph.nodes.seo_node import seo_node
   from graph.nodes.assemble_node import assemble_node
   from graph.nodes.upload_node import upload_node

2. Implement `build_pipeline() -> CompiledStateGraph`:

   builder = StateGraph(GhostCreatorState)

   # Register all nodes
   builder.add_node("research", research_node)
   builder.add_node("script", script_node)
   builder.add_node("script_critic", script_critic_node)
   builder.add_node("human_review", human_review_node)
   builder.add_node("parallel_spawn", spawn_parallel_tasks)   # fan-out node
   builder.add_node("image_worker", image_worker_node)
   builder.add_node("voiceover_worker", voiceover_worker_node)
   builder.add_node("seo", seo_node)
   builder.add_node("assemble", assemble_node)
   builder.add_node("upload", upload_node)

   # Linear edges
   builder.add_edge(START, "research")
   builder.add_edge("research", "script")
   builder.add_edge("script", "script_critic")
   builder.add_edge("script_critic", "human_review")

   # Conditional: after human review
   builder.add_conditional_edges(
       "human_review",
       route_after_review,
       {
           "parallel_generation": "parallel_spawn",
           "script_node": "script",          # regenerate with feedback
           END: END                           # max retries exhausted
       }
   )

   # Fan-out: parallel_spawn returns list of Send() objects
   # LangGraph routes each Send to the named node automatically
   builder.add_conditional_edges("parallel_spawn", lambda _: [], {})
   # The Send() objects from spawn_parallel_tasks point to "image_worker" and "voiceover_worker"

   # Fan-in: both workers converge at seo node
   builder.add_edge("image_worker", "seo")
   builder.add_edge("voiceover_worker", "seo")
   builder.add_edge("seo", "assemble")
   builder.add_edge("assemble", "upload")
   builder.add_edge("upload", END)

   # SQLite checkpointer — crash recovery + run history
   db_path = Path(config.get("pipeline.checkpoint_db", "ghost_runs.db"))
   checkpointer = SqliteSaver.from_conn_string(str(db_path))

   return builder.compile(checkpointer=checkpointer, interrupt_before=["human_review"])

3. Implement a singleton getter:
   _graph: CompiledStateGraph | None = None
   def get_pipeline() -> CompiledStateGraph:
       global _graph
       if _graph is None:
           _graph = build_pipeline()
       return _graph
```

---

---

# PHASE 10 — FastAPI Bridge (Graph ↔ Electron)

## Cursor Prompt 10.1 — New Pipeline API Route (LangGraph-based)

```
File to create: api/routes/graph_pipeline.py

This replaces the logic in api/routes/pipeline.py but keeps the SAME endpoint URLs
so the Electron frontend does NOT need to change.

All existing endpoints stay:
- POST /api/pipeline/start
- POST /api/pipeline/stop
- GET  /api/pipeline/script-review
- POST /api/pipeline/script/approve
- POST /api/pipeline/script/cancel
- POST /api/pipeline/retry
- WS   /api/pipeline/ws

But internally, they now talk to the LangGraph graph instead of PipelineRunner.

Implement:

A) POST /api/pipeline/start — new version:
   class StartBody(BaseModel):
       topic: str | None = None
       run_id: int | None = None
       mode: str = "shorts"                      # "shorts" | "documentary" | "custom_script"
       custom_script: str = ""                   # NEW: user's own script text

   def pipeline_start(body: StartBody) -> dict:
     1. Create a unique thread_id: f"run_{body.run_id or uuid4().hex[:8]}"
     2. Build initial state from graph.state.default_state():
        initial_state = {
            **default_state(),
            "topic": body.topic or "",
            "mode": body.mode,
            "user_custom_script": body.custom_script,
            "run_id": thread_id,
            "language": config.get("pipeline.voiceover_lang", "hinglish"),
        }
     3. Run the graph in a background thread (asyncio.to_thread or threading.Thread):
        graph = get_pipeline()
        config_dict = {"configurable": {"thread_id": thread_id}}
        # Run until first interrupt (human_review) or completion
        result = graph.invoke(initial_state, config=config_dict)
     4. Store thread_id in a module-level dict: _active_runs[thread_id] = {"status": "running"}
     5. Return: {"ok": True, "run_id": thread_id}

B) GET /api/pipeline/script-review — new version:
   1. Check all active run thread_ids for any graph paused at "human_review" interrupt.
   2. Use graph.get_state(config) to read the suspended state.
   3. If waiting: return {"waiting": True, "data": state.values["script"], ...}
   4. If not: return {"waiting": False, "data": None}

C) POST /api/pipeline/script/approve — new version:
   class ScriptApproveBody(BaseModel):
       title: str
       voiceover: str
       image_prompts: list[str]
       run_id: str         # thread_id

   def script_approve(body: ScriptApproveBody) -> dict:
     1. Use graph.update_state(config, {"review_decision": "approved", "script": {...}})
        to inject the user's approval + any edits into the suspended graph state.
     2. Resume the graph: graph.invoke(None, config=config_dict)
        (Passing None resumes from the last checkpoint.)
     3. Return {"ok": True}

D) POST /api/pipeline/script/cancel:
   1. graph.update_state(config, {"review_decision": "rejected", "script_attempts": MAX})
   2. graph.invoke(None, config=config_dict) — this will hit max_attempts → END
   3. Return {"ok": True}

E) POST /api/pipeline/retry:
   1. Read last_failed_node from graph state.
   2. Use graph.update_state to reset the retry counter for that node.
   3. Re-invoke the graph from the last checkpoint.
   4. Return {"ok": True}

NOTE: Keep the WebSocket /api/pipeline/ws endpoint exactly as-is from the existing
pipeline.py — the ProgressBroadcaster system still works the same way.
All nodes should call broadcaster.broadcast_sync() for progress events.
```

---

---

# PHASE 11 — Custom Script UI (Electron/React)

## Cursor Prompt 11.1 — Custom Script Input Tab in DocumentaryTab

```
File to modify: src/tabs/DocumentaryTab.tsx

Add a "Custom Script" mode to the existing documentary/shorts tab.

Requirements:

1. Add a new state variable:
   const [pipelineMode, setPipelineMode] = useState<"shorts" | "documentary" | "custom_script">("shorts")
   const [customScriptText, setCustomScriptText] = useState("")

2. Add a Mode Selector UI at the TOP of the pipeline controls section (before the topic input):
   Three toggle buttons styled like the existing Ghost Creator UI (dark theme, cyan accents):
   - 🤖 AI Mode (shorts)
   - 🎬 Documentary
   - ✍️ My Script  ← NEW

3. When "My Script" mode is selected:
   - Hide the topic input field (or make it optional: "Video topic (optional, for research context)")
   - Show a large textarea:
     placeholder="Apna script yahan likho... Koi bhi language chalega. AI isko polish karke video banana..."
     rows={12}
     maxLength={5000}
   - Show a character counter below: "{customScriptText.length} / 5000"
   - Show an info callout box:
     "✍️ Apne Script Se Video Banao
      Tumhara likha hua script AI ke through polish hoga — hook strong hoga,
      TTS-friendly banega — aur phir automatically video ban jayega.
      Script ka core message bilkul change nahi hoga."

4. Modify the existing Start Pipeline button's onClick handler:
   - If mode == "custom_script" and customScriptText.trim().length < 50:
     Show an inline error: "Script kam se kam 50 characters ka hona chahiye"
     Don't start pipeline.
   - Otherwise, POST to /api/pipeline/start with:
     { topic: topicInput, mode: pipelineMode, custom_script: customScriptText }

5. In the Script Review Modal (ScriptReviewModal.tsx):
   - Add a notice when mode == "custom_script":
     "📝 Yeh tumhara polished script hai. AI ne sirf delivery improve ki hai,
      original meaning preserve raha hai."
   - Keep all existing approve/reject/edit functionality unchanged.

6. Style everything consistently with the existing dark cyberpunk theme.
   Use existing CSS tokens from src/theme/tokens.ts.
```

---

---

# PHASE 12 — Analytics Feedback Loop Agent (NEW)

## Cursor Prompt 12.1 — Past Performance Hint Generator

```
File to create: graph/tools/analytics_tool.py

This tool connects to the existing yt_analytics.py system and generates
a "past_performance_hint" string injected into the research agent.

Implement `get_performance_hint(profile_index: int = 0) -> str`:

1. Import from core.yt_analytics:
   from core.yt_analytics import is_connected, get_analytics_data

2. If not is_connected(profile_index): return ""

3. Fetch analytics:
   data = get_analytics_data(profile_index, days=28)
   # data has: views, subscribers, top_videos: [{title, views, ctr, avg_watch_pct}]

4. Build a Gemini prompt to summarize learnings:
   """
   Here is YouTube analytics data from the last 28 days:
   Top videos by views: {top_videos_json}
   Total views: {total_views}, new subscribers: {new_subs}

   In 2-3 sentences, summarize:
   - What topics / styles performed BEST?
   - What should the creator make MORE of?
   - Any patterns in CTR or watch time?

   Be specific. Mention actual video titles if helpful.
   Output ONLY the 2-3 sentence summary.
   """

5. Return the summary string (or "" on any exception).

---

Also update graph/nodes/research_node.py:
Before building the research agent, call:
  past_hint = get_performance_hint()
  # inject into state before research runs
  # Pass past_hint as part of the agent's system prompt
```

---

---

# PHASE 13 — Agentic Error Recovery Node (NEW)

## Cursor Prompt 13.1 — Self-Healing Error Agent

```
File to create: graph/nodes/error_recovery_node.py

Context:
- Existing: modules/error_analyst.py — has analyse_error() which explains errors to users.
- NEW: This node autonomously FIXES errors without user intervention where possible.

Implement `error_recovery_node(state: GhostCreatorState) -> dict`:

This node is triggered when any other node fails (adds to state["errors"]).
Add it as a conditional edge from each main node.

1. If state["errors"] is empty: skip (return {})

2. Get the last error: last_error = state["errors"][-1]
   Get the failed node: failed_node = state["last_failed_node"]

3. Build a Pydantic model:
   class RecoveryPlan(BaseModel):
       is_recoverable: bool
       recovery_action: Literal["retry", "fallback", "skip", "abort"]
       fallback_instruction: str    # what to tell the next invocation
       user_message: str            # human-readable explanation

4. Ask Gemini to assess:
   """
   You are the Ghost Creator AI error recovery agent.
   A pipeline step failed. Decide if it can be recovered automatically.

   Failed node: {failed_node}
   Error: {last_error}
   Current retry count for this node: {retry_count}
   Max retries: 2

   Recovery options:
   - retry: try the same node again (good for network errors, rate limits)
   - fallback: use a simpler alternative (e.g., if Imagen fails, use a placeholder image)
   - skip: skip this optional step and continue
   - abort: this is unrecoverable, stop the pipeline

   Common recoveries:
   - Image generation API error → fallback (use stock image or solid color frame)
   - TTS network error → retry (up to 2x), then fallback to edge-tts
   - Research/web search error → fallback (use basic pytrends)
   - Assembly FFmpeg error → abort (critical step)
   - Upload error → skip (video is still made, just not uploaded)
   """

5. Execute the recovery plan:
   - "retry": increment retry_counts[failed_node], re-route to that node
   - "fallback": set a fallback flag in state, continue to next node
   - "skip": clear the error for this node, continue
   - "abort": return {END signal}

6. Always broadcast the user_message via the ProgressBroadcaster.

7. Return updated state with cleared errors for recoverable cases.
```

---

---

# PHASE 14 — Config Updates

## Cursor Prompt 14.1 — Add New Config Keys

```
File to modify: core/config_manager.py

Add the following new config keys with their defaults.
Follow the existing pattern of how config keys are registered.

New keys to add:
1. "pipeline.mode"                    default: "shorts"          (shorts | documentary | custom_script)
2. "pipeline.skip_human_review"       default: False             (auto-approve if critic score is high)
3. "pipeline.auto_approve_threshold"  default: 8.0               (critic score threshold for auto-approve)
4. "pipeline.checkpoint_db"           default: "ghost_runs.db"   (SQLite DB path for LangGraph checkpoints)
5. "pipeline.max_parallel_images"     default: 4                 (max simultaneous image generation workers)
6. "api_keys.tavily"                  default: ""                (Tavily search API key)
7. "pipeline.seo_enabled"             default: True              (run SEO node after approval)
8. "pipeline.error_recovery_enabled"  default: True              (run error recovery agent on failures)

Also update the Settings UI (src/tabs/SettingsTab.tsx):
Add a new "Agentic Pipeline" settings section with:
- Toggle: "Auto-approve scripts" (maps to pipeline.skip_human_review)
- Slider 6.0-10.0: "Auto-approve threshold" (maps to pipeline.auto_approve_threshold)
- Toggle: "SEO optimization" (maps to pipeline.seo_enabled)
- Toggle: "Error recovery agent" (maps to pipeline.error_recovery_enabled)
- Text input: "Tavily Search API Key" (maps to api_keys.tavily)
  With help text: "Optional. Get free key at tavily.com for better research quality."
```

---

---

# PHASE 15 — Final Integration + Backward Compatibility

## Cursor Prompt 15.1 — Bridge Old PipelineRunner to New Graph

```
File to modify: core/pipeline_runner.py

We want BACKWARD COMPATIBILITY. The old PipelineRunner must still work
so the app doesn't break during the transition.

Add the following at the top of pipeline_runner.py:

import os
USE_LANGGRAPH = os.environ.get("GHOST_USE_LANGGRAPH", "0") == "1"

Modify PipelineRunner.start() method:
def start(self, topic: str | None = None, mode: str = "shorts", custom_script: str = "") -> None:
    if USE_LANGGRAPH:
        # Delegate to new graph system
        from graph.pipeline import get_pipeline
        from graph.state import default_state
        # ... (same logic as graph_pipeline.py route handler)
    else:
        # Original threaded pipeline (unchanged)
        ...existing code...

This way:
- GHOST_USE_LANGGRAPH=0 → old system (default, safe)
- GHOST_USE_LANGGRAPH=1 → new LangGraph system (opt-in for testing)

Once all phases are tested, we flip the default to 1 and eventually remove the old system.
```

---

## Cursor Prompt 15.2 — Smoke Test Script

```
Create a new file: tests/test_graph_pipeline.py

Write a smoke test that:
1. Sets GHOST_USE_LANGGRAPH=1
2. Builds the pipeline graph: graph = build_pipeline()
3. Runs it with a mock state:
   initial = {
     **default_state(),
     "mode": "shorts",
     "topic": "AI in 2026",
     "run_id": "test_001",
     "max_script_attempts": 1,
   }
4. Mocks out actual API calls (patch modules.scripter.generate_script to return dummy data)
5. Mocks the human_review interrupt to auto-approve
6. Asserts the final state has:
   - script with voiceover_text
   - script_quality_score > 0
   - review_decision == "approved"
   - seo_optimized == True

Use pytest + unittest.mock.patch.
Run with: pytest tests/test_graph_pipeline.py -v
```

---

---

# 🗺️ Implementation Order & Time Estimate

| Phase | What | Est. Time | Priority |
|-------|------|-----------|----------|
| 1 | State schema + folder structure | 1 hr | 🔴 Critical |
| 2 | Research agent node | 2 hr | 🔴 Critical |
| 3 | Script node (custom script support!) | 2 hr | 🔴 Critical |
| 11 | Custom Script UI in Electron | 2 hr | 🔴 Critical |
| 4 | Script critic node | 1.5 hr | 🟠 High |
| 5 | Human review (interrupt) | 1 hr | 🟠 High |
| 9 | Main graph assembly | 1.5 hr | 🟠 High |
| 10 | FastAPI bridge | 2 hr | 🟠 High |
| 6 | Parallel image + voice | 1.5 hr | 🟡 Medium |
| 7 | SEO agent | 1 hr | 🟡 Medium |
| 8 | Assembly + upload wrappers | 1 hr | 🟡 Medium |
| 14 | Config updates + Settings UI | 1 hr | 🟡 Medium |
| 12 | Analytics feedback loop | 1.5 hr | 🟢 Enhancement |
| 13 | Error recovery agent | 2 hr | 🟢 Enhancement |
| 15 | Backward compat bridge + tests | 1 hr | 🟢 Enhancement |

**Total: ~22 hours of focused Cursor sessions**

---

# ⚡ Quick Start (Start Here First)

Run these 3 phases first to get the custom script feature + basic graph working:

```
Phase 1 → Phase 3 → Phase 11
```

This gives users the "My Script" mode immediately, even before the full LangGraph 
integration is complete. The script node (Phase 3) will polish the user's script 
and feed it into the EXISTING pipeline_runner.py system — no graph needed yet.

---

# 📝 Environment Variables Required

```
# .env additions
TAVILY_API_KEY=tvly-xxxxxxxxxxxxx    # optional but recommended
GHOST_USE_LANGGRAPH=0               # flip to 1 when ready to test
```

---

# 🏗️ Final Architecture Overview

```
User Input
  ├── "AI Mode"         → research_node → script_node → ...
  ├── "Documentary"     → research_node → script_node (doc mode) → ...
  └── "My Script" ✍️    → [skip research] → script_node (polish mode) → ...
                                               │
                                    script_critic_node (score 0-10)
                                               │
                              ┌────────────────┴─────────────────┐
                         score >= 8?                          score < 8?
                         skip_review=True?                    human reviews
                              │                                    │
                         auto-approved                      human_review_node
                              │                         (LangGraph interrupt())
                              └────────────────┬─────────────────┘
                                               │ approved
                                        seo_node (AI optimizes metadata)
                                               │
                                    parallel_spawn (Send())
                              ┌────────────────┴─────────────────┐
                         image_worker ×N                  voiceover_worker
                         (parallel, one per scene)        (runs simultaneously)
                              └────────────────┬─────────────────┘
                                               │ (fan-in)
                                         assemble_node
                                               │
                                          upload_node
                                               │
                                             END
                                    (SQLite checkpoint saved)
```
