# 0002. Choose each vendor by measured latency, per layer and region

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** AR-02, AR-04, VO-01, RG-03, RG-06
- **Plan decisions:** D22, D24, D25

## Context

The live call depends on several vendors: transport, speech to text, turn detection, the scriptwriter and safety models, and text to speech. Vendor claims about speed did not hold up when measured: a latency study from Australia found that about 200–250ms of the LLM host's time to first text was queueing on the provider, that Deepgram's Australian endpoint saves about 150–280ms per round trip over its global one, and that hosted text to speech served from outside Australia added about 465–520ms to first audio ([results](../../experiments/latency_probe/RESULTS.md)). No layer has yet met its target, and the product must serve both Australia and the US.

## Decision

No vendor is fixed for any layer. Each layer's vendor is chosen when that layer is built, from latency measured from the deployment regions (AWS Sydney and the US), against these targets: first audible sound within 300ms of the user's turn ending at p50 and 500ms at p95, and the first word of the real reply within 1.0s at p50 and 1.2s at p95. Vendors with in-region inference in both Australia and the US are preferred. Every vendor sits behind a typed interface so it can be replaced by configuration.

## Alternatives considered

- **Pick vendors once from published benchmarks.** Rejected: published figures are measured elsewhere, under other load.
- **Use one global vendor per layer.** Rejected: round trips across the Pacific alone exceed the latency budget for some layers.

## Consequences

Each layer's plan step starts with a measurement run from both regions, recorded in a decision record. The provider interfaces and region profiles must exist before any vendor-specific code. Measurements cost a little money each time; that spend is approved in advance.
