-- Stores all pushed contexts (category, merchant, customer, trigger).
-- (scope, context_id) is the logical key; version enforces ordering.
CREATE TABLE IF NOT EXISTS contexts (
    scope       TEXT NOT NULL,
    context_id  TEXT NOT NULL,
    version     INTEGER NOT NULL,
    payload     TEXT NOT NULL,   -- JSON blob
    stored_at   TEXT NOT NULL,   -- ISO-8601
    PRIMARY KEY (scope, context_id)
);

-- Tracks which suppression keys have fired in which conversations so we
-- never emit the same trigger twice.
CREATE TABLE IF NOT EXISTS suppression_keys (
    suppression_key   TEXT NOT NULL,
    conversation_id   TEXT NOT NULL,
    fired_at          TEXT NOT NULL,
    PRIMARY KEY (suppression_key, conversation_id)
);

-- Conversation turns — used for anti-repetition and intent detection.
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id  TEXT NOT NULL,
    turn_number      INTEGER NOT NULL,
    role             TEXT NOT NULL,   -- 'vera' | 'merchant' | 'customer'
    body             TEXT NOT NULL,
    ts               TEXT NOT NULL,
    PRIMARY KEY (conversation_id, turn_number)
);

-- Tracks which conversations have been closed (refused / ended).
CREATE TABLE IF NOT EXISTS closed_conversations (
    conversation_id  TEXT PRIMARY KEY,
    reason           TEXT NOT NULL,
    closed_at        TEXT NOT NULL
);
