"""Agent core — LLM orchestration with tool calling."""

from __future__ import annotations

import json
import logging
from typing import Optional

import litellm

from ..models.song import TasteProfile
from ..models.store import Store
from ..agent.tools import TOOL_SCHEMAS, ToolExecutor
from ..config import MelodiaConfig

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are Melodia, a personal AI music curator who deeply understands {user_name}'s taste.

## Your Taste Understanding
{taste_narrative}

## Anti-Patterns (avoid these)
{anti_patterns}

## Core Principles
1. HIT RATE over novelty. Only recommend songs you are confident about.
2. When you find a match, DEEP-DIVE first. Explore that dimension thoroughly before branching.
3. "Good or not" is the only criterion. No rigid rules about time-of-day or genre quotas.
4. You judge music by ALL dimensions: musicality, emotional resonance, atmosphere, intuition.
5. Moderate exploration: 80% confidence matches, 20% calculated risks.
6. Always explain WHY. The user wants to understand your reasoning.
7. When corrected, pivot immediately. Do not defend bad recommendations.

## Recommendation Strategy
- For vibe/mood requests: use recommend_by_vibe with rich descriptions
- For song exploration: use recommend_similar with specific song_id
- For deep-dives: use deep_dive, then follow the most promising dimension
- After 2-3 good recommendations in a direction, broaden slightly
- If a recommendation misses, analyze why before trying again

## Response Format
- Keep responses concise (2-4 sentences + recommendation cards)
- Each recommendation: song name, artist, and a one-line reason connecting to taste
- When deep-diving, show the dimension map
- Never list more than 5 songs at once

## Session Context
{session_context}"""


class Agent:
    """Melodia's agent core — single LLM with tool calling."""

    def __init__(self, config: MelodiaConfig, store: Store, tool_executor: ToolExecutor):
        self.config = config
        self.store = store
        self.tool_executor = tool_executor
        self._messages: list[dict] = []

    def _build_system_prompt(self, session_context: str = "") -> str:
        profile = self.store.load_taste_profile()
        narrative = profile.narrative if profile else "Taste profile not yet generated. Recommend based on the user's explicit request."
        anti_patterns = "\n".join(f"- {p}" for p in (profile.anti_patterns if profile else [])) or "None yet"

        return SYSTEM_PROMPT_TEMPLATE.format(
            user_name="you",
            taste_narrative=narrative,
            anti_patterns=anti_patterns,
            session_context=session_context or "New session.",
        )

    async def chat(self, user_message: str, session_context: str = "") -> str:
        """Process a user message and return Melodia's response.

        Handles tool calling loop: LLM → tool call → execute → LLM → response.
        """
        # Reset messages if this is a fresh context
        if not self._messages:
            self._messages = [
                {"role": "system", "content": self._build_system_prompt(session_context)},
            ]

        self._messages.append({"role": "user", "content": user_message})

        # Tool calling loop (max 3 iterations to prevent infinite loops)
        for _ in range(3):
            response = litellm.completion(
                model=self.config.llm.model,
                messages=self._messages,
                tools=TOOL_SCHEMAS,
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens,
                **({"api_base": self.config.llm.api_base} if self.config.llm.api_base else {}),
                **({"api_key": self.config.llm.api_key} if self.config.llm.api_key else {}),
            )

            message = response.choices[0].message

            # No tool calls — return the response
            if not message.tool_calls:
                self._messages.append({"role": "assistant", "content": message.content})
                return message.content or ""

            # Execute tool calls
            self._messages.append(message.model_dump())

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                logger.info(f"Tool call: {fn_name}({fn_args})")
                result = await self.tool_executor.execute(fn_name, fn_args)

                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        # If we exhausted the loop, get a final response without tools
        response = litellm.completion(
            model=self.config.llm.model,
            messages=self._messages,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
            **({"api_base": self.config.llm.api_base} if self.config.llm.api_base else {}),
            **({"api_key": self.config.llm.api_key} if self.config.llm.api_key else {}),
        )
        content = response.choices[0].message.content or ""
        self._messages.append({"role": "assistant", "content": content})
        return content

    def reset_session(self):
        """Reset conversation history for a new session."""
        self._messages = []