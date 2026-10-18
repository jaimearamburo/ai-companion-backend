"""Typed, strict models for everything that crosses a boundary of the system."""

from companion.contracts.bots import BotDefinition, BotSafetyRules, MemoryPolicy
from companion.contracts.dispatch import DispatchMetadata, Presets, Region, UserRole
from companion.contracts.evals import (
    EvalRunResult,
    EvalScenario,
    ExpectedEndState,
    ExpectedToolCall,
    ScenarioSession,
)
from companion.contracts.memory import MemoryKind, MemoryRecord, MemoryType
from companion.contracts.safety import SafetyCategory, SafetyVerdict
from companion.contracts.script import NON_VERBAL_CUES, Script, ScriptLine
from companion.contracts.tools import (
    ForgetMemoryInput,
    ForgetMemoryOutput,
    ListMemoriesInput,
    ListMemoriesOutput,
    MemoryItem,
    RecallMemoryInput,
    RecallMemoryOutput,
    ToolError,
    ToolErrorCode,
    ToolName,
)

__all__ = [
    "NON_VERBAL_CUES",
    "BotDefinition",
    "BotSafetyRules",
    "DispatchMetadata",
    "EvalRunResult",
    "EvalScenario",
    "ExpectedEndState",
    "ExpectedToolCall",
    "ForgetMemoryInput",
    "ForgetMemoryOutput",
    "ListMemoriesInput",
    "ListMemoriesOutput",
    "MemoryItem",
    "MemoryKind",
    "MemoryPolicy",
    "MemoryRecord",
    "MemoryType",
    "Presets",
    "RecallMemoryInput",
    "RecallMemoryOutput",
    "Region",
    "SafetyCategory",
    "SafetyVerdict",
    "ScenarioSession",
    "Script",
    "ScriptLine",
    "ToolError",
    "ToolErrorCode",
    "ToolName",
    "UserRole",
]
