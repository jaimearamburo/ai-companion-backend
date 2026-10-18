# 0009. Don't partition tables until volume needs it

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** EN-05, MT-12
- **Plan decisions:** D41

## Context

`messages` was created hash-partitioned by `user_id` into 16 partitions, and the memories design followed the same pattern, on the grounds that partitioning is cheap to set up and expensive to add to a large live table. At this app's volume (thousands to low millions of rows) a single table performs well, so partitioning added cost with no benefit: 16 extra tables per partitioned table in the dashboard, a loop in every migration to secure each partition, and `user_id` forced into every key and unique constraint.

## Decision

Tables are plain until measurements show they need partitioning. Migration `20261018023000` replaces the partitioned `messages` with a plain table, and the memories table is designed unpartitioned. User-owned tables keep their same-user composite references (`(user_id, session_id) → sessions (user_id, id)`), which is what guarantees a row can't be attached to another user's data; that guarantee never depended on partitioning.

Partitioning is reconsidered when any of these holds for a table: it passes roughly 50 million rows; vacuum or index maintenance on it measurably affects query latency; or deleting a user's data becomes slow enough to matter. The path then is declarative hash partitioning by `user_id`: create the partitioned table beside the old one, copy rows across in batches, and swap names in one transaction, as migration `20261018023000` does in reverse.

## Alternatives considered

- **Keep partitioning.** Rejected: complexity now for a benefit that only appears at volumes this app may never reach.
- **Partition by time instead.** Rejected: queries are per user and per call, not per time range.

## Consequences

One table per entity in the dashboard and simpler migrations. Primary keys are plain `id`; tables that others reference by user also carry a unique `(user_id, id)` so composite references keep working. Adding partitioning later is a planned migration with a stated trigger, not a surprise.
