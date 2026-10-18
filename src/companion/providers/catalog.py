"""The provider registry: preset catalogue, region profiles and their rules.

The catalogue (presets.toml) and profiles (regions.toml) are validated together
when loaded, so a misspelt preset, a preset of the wrong kind or an incompatible
default fails at startup rather than in a call.
"""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Annotated, Literal, Self

from pydantic import StringConstraints, ValidationError, model_validator

from companion.config import ConfigurationError, Credential, Settings
from companion.contracts import Presets, Region
from companion.contracts._base import Contract, PresetName

type PresetKind = Literal["stt", "tts", "llm", "safety", "turn_detector", "speculative_trigger"]
type AwsRegion = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[a-z]+)+-\d$")]

CREDENTIAL_ENV_VARS: Mapping[Credential, str] = {
    "deepgram": "DEEPGRAM_API_KEY",
    "fish": "FISH_API_KEY",
    "groq": "GROQ_API_KEY",
    "bedrock": "BEDROCK_API_KEY",
    "inworld": "INWORLD_API_KEY",
}

_LAYERS: tuple[tuple[str, PresetKind], ...] = (
    ("stt", "stt"),
    ("tts", "tts"),
    ("llm", "llm"),
    ("safety", "safety"),
    ("turn_detector", "turn_detector"),
    ("speculative_trigger", "speculative_trigger"),
)


class PresetSpec(Contract):
    kind: PresetKind
    vendor: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+$")]
    model: str | None = None
    endpoint: Annotated[str, StringConstraints(pattern=r"^https://\S+$")] | None = None
    credential: Credential | None = None
    # STT capabilities that decide turn detection and the "auto" trigger.
    reports_end_of_turn: bool = False
    emits_preflight: bool = False

    @model_validator(mode="after")
    def _capabilities_only_on_stt(self) -> Self:
        if self.kind != "stt" and (self.reports_end_of_turn or self.emits_preflight):
            raise ValueError("only STT presets have end-of-turn or preflight capabilities")
        return self


class RoleChoice(Contract):
    """A primary preset and an optional fallback for one LLM role."""

    primary: PresetName
    fallback: PresetName | None = None

    @model_validator(mode="after")
    def _fallback_differs(self) -> Self:
        if self.fallback == self.primary:
            raise ValueError("a fallback must differ from the primary")
        return self


class RegionProfile(Contract):
    agent_name: Annotated[str, StringConstraints(pattern=r"^companion-[a-z0-9-]+$")]
    aws_region: AwsRegion
    stt: PresetName
    tts: PresetName
    llm: RoleChoice
    safety: RoleChoice
    turn_detector: PresetName
    speculative_trigger: PresetName
    shared_services_aws_region: AwsRegion

    def preset_names(self) -> dict[str, tuple[PresetName, PresetKind]]:
        """Every preset the profile uses, labelled by where it's used."""
        names: dict[str, tuple[PresetName, PresetKind]] = {
            "stt": (self.stt, "stt"),
            "tts": (self.tts, "tts"),
            "llm.primary": (self.llm.primary, "llm"),
            "safety.primary": (self.safety.primary, "safety"),
            "turn_detector": (self.turn_detector, "turn_detector"),
            "speculative_trigger": (self.speculative_trigger, "speculative_trigger"),
        }
        if self.llm.fallback:
            names["llm.fallback"] = (self.llm.fallback, "llm")
        if self.safety.fallback:
            names["safety.fallback"] = (self.safety.fallback, "safety")
        return names


class ProviderCatalog(Contract):
    presets: Mapping[PresetName, PresetSpec]
    regions: Mapping[Region, RegionProfile]

    @model_validator(mode="after")
    def _profiles_consistent(self) -> Self:
        problems: list[str] = []
        for region in ("au", "us"):
            if region not in self.regions:
                problems.append(f"no profile for region {region}")
        for region, profile in self.regions.items():
            for where, (name, kind) in profile.preset_names().items():
                problems += [f"{region}.{where}: {p}" for p in self.kind_problems(name, kind)]
            if not problems:
                problems += [
                    f"{region}: {p}"
                    for p in self.compatibility_problems(profile.stt, profile.turn_detector)
                ]
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def kind_problems(self, name: str, kind: PresetKind) -> list[str]:
        spec = self.presets.get(name)
        if spec is None:
            return [f"unknown preset {name!r}"]
        if spec.kind != kind:
            return [f"{name!r} is a {spec.kind} preset, not {kind}"]
        return []

    def compatibility_problems(self, stt: str, turn_detector: str) -> list[str]:
        if turn_detector == "stt_native" and not self.presets[stt].reports_end_of_turn:
            return [
                f"stt_native turn detection needs an STT that reports end of turn; {stt} doesn't"
            ]
        return []

    def resolve_trigger(self, stt: str, trigger: str) -> str:
        """Resolve "auto": LiveKit's preemptive generation when the STT emits preflight
        transcripts, otherwise our own transcript rules."""
        if trigger != "auto":
            return trigger
        return "livekit_preemptive" if self.presets[stt].emits_preflight else "transcript_rules"


@cache
def load_catalog() -> ProviderCatalog:
    """Load and validate the packaged catalogue and profiles, or raise ConfigurationError."""
    package = files("companion.providers")
    try:
        presets = tomllib.loads(package.joinpath("presets.toml").read_text(encoding="utf-8"))
        regions = tomllib.loads(package.joinpath("regions.toml").read_text(encoding="utf-8"))
        return ProviderCatalog.model_validate(
            {"presets": presets["presets"], "regions": regions["regions"]}
        )
    except (tomllib.TOMLDecodeError, KeyError, ValidationError) as error:
        raise ConfigurationError(f"Invalid provider catalogue: {error}") from None


def missing_credentials(
    catalog: ProviderCatalog, names: list[str], settings: Settings
) -> list[str]:
    """Environment variables that must be set for these presets but aren't."""
    missing: list[str] = []
    for name in names:
        credential = catalog.presets[name].credential
        if credential is not None and settings.api_key(credential) is None:
            variable = CREDENTIAL_ENV_VARS[credential]
            if variable not in missing:
                missing.append(variable)
    return missing


def check_region_ready(catalog: ProviderCatalog, settings: Settings) -> RegionProfile:
    """At worker startup: the worker's region profile, with every key it needs present."""
    profile = catalog.regions[settings.worker_region]
    names = [name for name, _ in profile.preset_names().values()]
    missing = missing_credentials(catalog, names, settings)
    if missing:
        raise ConfigurationError(
            f"Region {settings.worker_region} needs these variables set: {', '.join(missing)}"
        )
    return profile


class PresetRejectedError(Exception):
    """A call's chosen presets are unknown, the wrong kind, incompatible or unconfigured."""


@dataclass(frozen=True, slots=True)
class ResolvedProviders:
    """The presets one call will use. The trigger is resolved, never "auto"."""

    region: Region
    stt: str
    tts: str
    llm: str
    llm_fallback: str | None
    safety: str
    safety_fallback: str | None
    turn_detector: str
    speculative_trigger: str


def resolve_providers(
    catalog: ProviderCatalog, region: Region, requested: Presets, settings: Settings
) -> ResolvedProviders:
    """Check a call's presets at session start and pick fallbacks from the region profile."""
    problems: list[str] = []
    for field, kind in _LAYERS:
        problems += [
            f"{field}: {p}" for p in catalog.kind_problems(getattr(requested, field), kind)
        ]
    if problems:
        raise PresetRejectedError("; ".join(problems))

    problems += catalog.compatibility_problems(requested.stt, requested.turn_detector)
    profile = catalog.regions[region]

    def fallback(choice: RoleChoice, chosen: str) -> str | None:
        # The profile's first choice that isn't the preset already in use.
        return next(
            (name for name in (choice.primary, choice.fallback) if name and name != chosen), None
        )

    llm_fallback = fallback(profile.llm, requested.llm)
    safety_fallback = fallback(profile.safety, requested.safety)
    used = [getattr(requested, field) for field, _ in _LAYERS]
    used += [name for name in (llm_fallback, safety_fallback) if name is not None]
    missing = missing_credentials(catalog, used, settings)
    if missing:
        problems.append(f"not configured on this worker: {', '.join(missing)}")
    if problems:
        raise PresetRejectedError("; ".join(problems))

    return ResolvedProviders(
        region=region,
        stt=requested.stt,
        tts=requested.tts,
        llm=requested.llm,
        llm_fallback=llm_fallback,
        safety=requested.safety,
        safety_fallback=safety_fallback,
        turn_detector=requested.turn_detector,
        speculative_trigger=catalog.resolve_trigger(requested.stt, requested.speculative_trigger),
    )
