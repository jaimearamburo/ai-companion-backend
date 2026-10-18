"""Provider registry: interfaces, fakes, the preset catalogue and region profiles."""

from companion.providers.catalog import (
    PresetRejectedError,
    ProviderCatalog,
    RegionProfile,
    ResolvedProviders,
    check_region_ready,
    load_catalog,
    resolve_providers,
)
from companion.providers.interfaces import ChatModel, SafetyClassifier

__all__ = [
    "ChatModel",
    "PresetRejectedError",
    "ProviderCatalog",
    "RegionProfile",
    "ResolvedProviders",
    "SafetyClassifier",
    "check_region_ready",
    "load_catalog",
    "resolve_providers",
]
