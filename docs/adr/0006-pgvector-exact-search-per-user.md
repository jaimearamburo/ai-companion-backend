# 0006. Store memories in Postgres with pgvector and search each user's memories exactly

- **Status:** Accepted
- **Date:** 2026-10-18
- **Checklist items:** MT-04, MT-07, MT-09, MT-12
- **Plan decisions:** D5, D6, D12

## Context

Bots search a user's long-term memories by meaning. One user has thousands of memories, not millions. The database already enforces that a memory can only belong to its own user, and deleting an account must remove everything. pgvector applies filters after an approximate index scan, so a shared approximate index can return few or no rows for a single user.

## Decision

Memories, their vectors and the bots that witnessed them live in the existing Supabase Postgres database, using pgvector with half-precision vectors. Search scans one user's memories exactly, narrowed by the primary key's user prefix, with no approximate index for now. Access goes through a `VectorStore` interface, with an in-memory implementation for tests. The embedding model is chosen by benchmark and recorded per row.

## Alternatives considered

- **Qdrant or Chroma as a separate vector database.** Rejected: a second store to run, keep in sync and clear on deletion, for a scale this app will not reach.
- **An HNSW index.** Deferred: worth revisiting only if individual histories grow very large.

## Consequences

One store keeps memories, witnesses and deletions in a single transaction, at no extra cost. Exact-search latency must be benchmarked on a realistic history. A change of embedding model requires re-embedding every memory with the re-embed script.
