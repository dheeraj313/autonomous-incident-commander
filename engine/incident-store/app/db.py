import json
from uuid import UUID

import asyncpg

from . import config


async def _init_connection(conn: asyncpg.Connection) -> None:
    # incident_events.payload is JSONB; teach asyncpg to (de)serialize it as a
    # plain Python dict instead of returning/expecting raw JSON text.
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog", format="text"
    )


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=config.DATABASE_URL, min_size=1, max_size=5, init=_init_connection)


async def append_event(pool: asyncpg.Pool, incident_id: UUID, event_type: str, payload: dict) -> dict:
    """Append-only insert. Never UPDATE/DELETE rows in this table - the whole
    point of the event store is that an incident's history is reconstructed by
    replaying its ordered events, not by mutating shared state in place."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serializes concurrent appends to the same incident so sequence_no
            # stays gap-free/unique without a separate counter table.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(incident_id))
            row = await conn.fetchrow(
                """
                INSERT INTO incidents.incident_events (incident_id, sequence_no, event_type, payload)
                SELECT $1, COALESCE(MAX(sequence_no), 0) + 1, $2, $3::jsonb
                FROM incidents.incident_events WHERE incident_id = $1
                RETURNING sequence_no, event_type, payload, created_at
                """,
                incident_id,
                event_type,
                payload,
            )
    return dict(row)


async def fetch_events(pool: asyncpg.Pool, incident_id: UUID) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT sequence_no, event_type, payload, created_at
            FROM incidents.incident_events
            WHERE incident_id = $1
            ORDER BY sequence_no
            """,
            incident_id,
        )
    return [dict(r) for r in rows]


async def fetch_incident_ids(pool: asyncpg.Pool) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT incident_id,
                   MIN(created_at) AS started_at,
                   MAX(created_at) AS last_event_at,
                   COUNT(*) AS event_count
            FROM incidents.incident_events
            GROUP BY incident_id
            ORDER BY started_at DESC
            """
        )
    return [dict(r) for r in rows]
