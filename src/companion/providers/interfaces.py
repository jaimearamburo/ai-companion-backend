"""The interfaces the rest of the system depends on, instead of on vendors.

Each is implemented by an adapter per provider and by a fake for tests. Speech
to text and text to speech get theirs with the voice pipeline, where LiveKit's
own plugin types are the natural boundary.
"""

from collections.abc import AsyncIterator
from typing import Protocol

from companion.contracts import SafetyVerdict
from companion.contracts.llm import ChatEvent, ChatRequest


class ChatModel(Protocol):
    """A chat LLM that streams its reply."""

    @property
    def preset(self) -> str:
        """The preset this model was built from, for logs and traces."""
        ...

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        """Stream text deltas and tool calls, ending with exactly one Finished event."""
        ...


class SafetyClassifier(Protocol):
    """A safety model that classifies a user's words."""

    @property
    def preset(self) -> str: ...

    async def classify(self, text: str) -> SafetyVerdict:
        """Return a verdict, or raise; the safety gate treats any error as unsafe."""
        ...
