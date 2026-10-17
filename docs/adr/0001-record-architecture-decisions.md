# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** EN-05
- **Plan decisions:** D31

## Context

Significant choices in this project (vendors, safety behaviour, memory storage, where code runs) were recorded inside ARCHITECTURE.md, mixed with the description of the system. That makes it hard to see when a choice was made, what was rejected, and why.

## Decision

Each significant decision gets a short record in `docs/adr/`, numbered in order and written from [the template](0000-template.md). A record is never rewritten after it is accepted; a later record supersedes it. PLAN.md section 3 lists every decision briefly and links to its record where one exists; ARCHITECTURE.md describes the system as it is.

## Alternatives considered

- **Keep decisions in ARCHITECTURE.md only.** Rejected: rejected options and dates get lost as the document is edited.
- **Decisions in issue comments.** Rejected: hard to find, and they live outside the repository.

## Consequences

Reviewers can read the reasoning behind each choice in one place. Every plan step that makes a significant decision adds a record in the same change.
