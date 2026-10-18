"""The packaged catalogue loads; broken catalogues and unconfigured presets are rejected."""

import copy
import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from companion.config import ConfigurationError, Settings
from companion.contracts import Presets, Region
from companion.providers import catalog as catalog_module
from companion.providers.catalog import (
    PresetRejectedError,
    ProviderCatalog,
    check_region_ready,
    load_catalog,
    resolve_providers,
)

ALL_KEYS = {
    "deepgram_api_key": "d",
    "fish_api_key": "f",
    "groq_api_key": "g",
    "bedrock_api_key": "b",
    "inworld_api_key": "i",
}


def settings(**keys: str | None) -> Settings:
    values: dict[str, Any] = {
        "livekit_url": "wss://example.livekit.cloud",
        "livekit_api_key": "k",
        "livekit_api_secret": "s",
        "redis_url": "rediss://example:6379",
        "supabase_db_url": "postgresql://example/db",
        **ALL_KEYS,
        **keys,
    }
    return Settings.model_validate({k: v for k, v in values.items() if v is not None})


def raw() -> dict[str, Any]:
    package = files("companion.providers")
    presets = tomllib.loads(package.joinpath("presets.toml").read_text(encoding="utf-8"))
    regions = tomllib.loads(package.joinpath("regions.toml").read_text(encoding="utf-8"))
    return {"presets": presets["presets"], "regions": regions["regions"]}


def presets(**changes: str) -> Presets:
    defaults = {
        "stt": "deepgram_nova3_au",
        "tts": "fish_s21_hosted",
        "llm": "bedrock_gptoss120b_syd",
        "safety": "groq_safeguard20b",
        "turn_detector": "livekit_v1_mini",
        "speculative_trigger": "auto",
    }
    return Presets.model_validate({**defaults, **changes})


def test_packaged_catalogue_is_valid_and_has_both_regions() -> None:
    catalog = load_catalog()
    assert set(catalog.regions) == {"au", "us"}
    assert catalog.regions["au"].agent_name == "companion-au"


def broken(change: str) -> dict[str, Any]:
    data = copy.deepcopy(raw())
    au = data["regions"]["au"]
    match change:
        case "unknown_preset":
            au["stt"] = "acme_stt"
        case "wrong_kind":
            au["tts"] = "deepgram_nova3_au"
        case "incompatible_turn_detection":
            au["turn_detector"] = "stt_native"
        case "fallback_same_as_primary":
            au["llm"]["fallback"] = au["llm"]["primary"]
        case "missing_region":
            del data["regions"]["us"]
        case "capability_on_non_stt":
            data["presets"]["fish_s21_hosted"]["emits_preflight"] = True
        case "bad_endpoint":
            data["presets"]["groq_gptoss120b"]["endpoint"] = "http://api.groq.com"
    return data


@pytest.mark.parametrize(
    "change",
    [
        "unknown_preset",
        "wrong_kind",
        "incompatible_turn_detection",
        "fallback_same_as_primary",
        "missing_region",
        "capability_on_non_stt",
        "bad_endpoint",
    ],
)
def test_broken_catalogue_fails_at_load(change: str) -> None:
    with pytest.raises(ValidationError):
        ProviderCatalog.model_validate(broken(change))


def test_region_profile_requires_only_its_own_keys() -> None:
    catalog = load_catalog()
    # The au profile uses Deepgram, Fish, Bedrock and Groq; Inworld isn't needed.
    check_region_ready(catalog, settings(inworld_api_key=None))

    with pytest.raises(ConfigurationError) as caught:
        check_region_ready(catalog, settings(fish_api_key=None, groq_api_key=None))
    assert "FISH_API_KEY" in str(caught.value)
    assert "GROQ_API_KEY" in str(caught.value)


def test_auto_trigger_resolves_by_stt_capability() -> None:
    catalog = load_catalog()
    deepgram = resolve_providers(catalog, "au", presets(), settings())
    assert deepgram.speculative_trigger == "livekit_preemptive"
    inworld = resolve_providers(catalog, "au", presets(stt="inworld_stt1"), settings())
    assert inworld.speculative_trigger == "transcript_rules"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"llm": "acme_llm"}, "unknown preset"),
        ({"tts": "groq_gptoss120b"}, "is a llm preset, not tts"),
        ({"turn_detector": "stt_native"}, "needs an STT that reports end of turn"),
    ],
)
def test_invalid_session_presets_are_rejected(changes: dict[str, str], expected: str) -> None:
    with pytest.raises(PresetRejectedError, match=expected):
        resolve_providers(load_catalog(), "au", presets(**changes), settings())


def test_stt_native_is_allowed_with_an_end_of_turn_stt() -> None:
    chosen = presets(stt="deepgram_flux_au", turn_detector="stt_native")
    assert resolve_providers(load_catalog(), "au", chosen, settings()).turn_detector == "stt_native"


def test_presets_needing_unset_keys_are_rejected() -> None:
    with pytest.raises(PresetRejectedError, match="INWORLD_API_KEY"):
        resolve_providers(
            load_catalog(), "au", presets(stt="inworld_stt1"), settings(inworld_api_key=None)
        )


@pytest.mark.parametrize(
    ("region", "llm", "expected_fallback"),
    [
        ("au", "bedrock_gptoss120b_syd", "groq_gptoss120b"),
        ("au", "groq_gptoss120b", "bedrock_gptoss120b_syd"),
        ("us", "bedrock_gptoss120b_syd", "bedrock_gptoss120b_use1"),
    ],
)
def test_fallback_is_the_profiles_first_other_choice(
    region: Region, llm: str, expected_fallback: str
) -> None:
    resolved = resolve_providers(load_catalog(), region, presets(llm=llm), settings())
    assert resolved.llm_fallback == expected_fallback


def test_no_fallback_when_the_profile_has_none_left() -> None:
    resolved = resolve_providers(load_catalog(), "us", presets(), settings())
    assert resolved.safety_fallback is None


def test_explicit_trigger_is_kept() -> None:
    chosen = presets(speculative_trigger="vad_silence")
    resolved = resolve_providers(load_catalog(), "au", chosen, settings())
    assert resolved.speculative_trigger == "vad_silence"


@pytest.mark.parametrize(
    ("presets_toml", "regions_toml"),
    [("[presets.bad", "[regions]"), ("[nothing]", "[regions]")],
)
def test_unreadable_catalogue_fails_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, presets_toml: str, regions_toml: str
) -> None:
    (tmp_path / "presets.toml").write_text(presets_toml, encoding="utf-8")
    (tmp_path / "regions.toml").write_text(regions_toml, encoding="utf-8")
    monkeypatch.setattr(catalog_module, "files", lambda _package: tmp_path)
    load_catalog.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="Invalid provider catalogue"):
            load_catalog()
    finally:
        load_catalog.cache_clear()
