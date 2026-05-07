"""Feedback loop — taste profile evolution from implicit + explicit feedback."""

from __future__ import annotations

import logging

from ..models.song import Feedback, TasteProfile
from ..models.store import Store
from ..engine.vector_store import VectorStore
from ..engine.taste_profile import generate_taste_profile

logger = logging.getLogger(__name__)

# Threshold for triggering a full profile regeneration
REGENERATION_THRESHOLD = 20  # interactions


class FeedbackProcessor:
    """Process feedback and evolve the taste profile."""

    def __init__(self, store: Store, vector_store: VectorStore, llm_model: str = "openai/4.0Ultra", api_base: str = "", api_key: str = ""):
        self.store = store
        self.vector_store = vector_store
        self.llm_model = llm_model
        self.api_base = api_base
        self.api_key = api_key

    def process_feedback(self, feedback: Feedback):
        """Process a single feedback event and update taste if needed."""
        # Log the feedback
        self.store.log_feedback(feedback)

        # Update song counters
        song = self.store.get_song(feedback.song_id)
        if song:
            if feedback.feedback_type == "play_complete":
                song.play_count += 1
            elif feedback.feedback_type == "skip":
                song.skip_count += 1
            elif feedback.feedback_type == "favorite":
                song.is_favorite = True
            self.store.upsert_song(song)

        # Check if we should regenerate the profile
        self._maybe_regenerate()

    def process_dialogue_feedback(self, song_id: int, text: str):
        """Extract feedback from dialogue text and apply it.

        Examples: "太吵了" → anti-pattern, "喜欢这种氛围" → positive signal
        """
        # Add to anti-patterns if negative
        negative_keywords = ["不要", "不喜欢", "太", "别", "避免", "吵", "烦"]
        is_negative = any(kw in text for kw in negative_keywords)

        profile = self.store.load_taste_profile()
        if profile:
            if is_negative:
                profile.anti_patterns.append(text)
                self.store.save_taste_profile(profile)
            # Positive feedback is captured through play/favorite behavior

        # Log as dialogue feedback
        fb = Feedback(
            song_id=song_id,
            feedback_type="dialogue",
            value=-0.5 if is_negative else 0.5,
            context=text,
        )
        self.store.log_feedback(fb)
        self._maybe_regenerate()

    def _maybe_regenerate(self):
        """Regenerate taste profile if enough new interactions have accumulated."""
        profile = self.store.load_taste_profile()
        if not profile:
            return

        current_count = self.store.feedback_count()
        last_count = profile.interaction_count

        if current_count - last_count >= REGENERATION_THRESHOLD:
            logger.info(f"Regenerating taste profile ({current_count - last_count} new interactions)")
            songs = self.store.get_all_songs()
            new_profile = generate_taste_profile(
                songs, self.store, self.vector_store,
                llm_model=self.llm_model, api_base=self.api_base, api_key=self.api_key,
            )
            new_profile.interaction_count = current_count
            self.store.save_taste_profile(new_profile)
            logger.info("Taste profile regenerated")
