-- All users that are seen by bot
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tg_user_id      BIGINT UNSIGNED NOT NULL UNIQUE,
    username        VARCHAR(64),
    first_name      VARCHAR(128),
    last_name       VARCHAR(128),
    avatar_url      VARCHAR(512),
    language_code   VARCHAR(10),
    last_seen       DATETIME,
    registered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    status          ENUM('online','offline','away') DEFAULT 'offline',
    allow_add_me    BOOLEAN DEFAULT TRUE,
    allow_call_from ENUM('all','contacts','friends','none') DEFAULT 'all',
    show_status_to  ENUM('all','contacts','friends','none') DEFAULT 'all',
    notifications_enabled BOOLEAN DEFAULT TRUE,
    deleted_at      DATETIME DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Address book, friends
CREATE TABLE IF NOT EXISTS user_contacts (
    user_id     BIGINT UNSIGNED NOT NULL,       -- who has been add
    contact_id  BIGINT UNSIGNED NOT NULL,       -- whom
    is_friend   BOOLEAN DEFAULT FALSE,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, contact_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS user_blacklist (
    user_id     BIGINT UNSIGNED NOT NULL,      -- who blocks
    blocked_id  BIGINT UNSIGNED NOT NULL,      -- who is blocked
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, blocked_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS invites (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    inviter_id   BIGINT UNSIGNED NOT NULL,
    invitee_id   BIGINT UNSIGNED DEFAULT NULL,
    room_id      VARCHAR(64) NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    accepted_at  DATETIME DEFAULT NULL,
    status       ENUM('sent','accepted','expired') DEFAULT 'sent',
    FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Call sessions log (normalized)
CREATE TABLE IF NOT EXISTS call_logs (
    id                 BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    room_uid           VARCHAR(128) NOT NULL,                -- room identifier (string)
    owner_id           BIGINT UNSIGNED NOT NULL,             -- FK to users.id (room owner)
    started_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at           DATETIME DEFAULT NULL,
    duration_sec       INT UNSIGNED DEFAULT NULL,            -- computed on finalize
    status             ENUM('created','active','completed','solo','failed') NOT NULL DEFAULT 'created',
    participant_count  INT UNSIGNED NOT NULL DEFAULT 0,      -- distinct participants count (excluding owner)
    participants_json  TEXT DEFAULT NULL,                    -- denormalized distinct list for quick APIs
    recordings_json    TEXT DEFAULT NULL,                    -- denormalized list of file names recorded in this call
    metadata           JSON DEFAULT NULL,                    -- arbitrary diagnostics (ended_reason, etc.)
    KEY idx_room_started (room_uid, started_at),
    KEY idx_owner_started (owner_id, started_at),
    KEY idx_status (status),
    CONSTRAINT fk_call_logs_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Participants per call (distinct users involved in a call session)
CREATE TABLE IF NOT EXISTS call_participants (
    id                   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id              BIGINT UNSIGNED NOT NULL,
    user_id              BIGINT UNSIGNED NOT NULL,     -- FK to users.id
    first_joined_at      DATETIME NOT NULL,
    last_left_at         DATETIME DEFAULT NULL,
    total_duration_sec   INT UNSIGNED NOT NULL DEFAULT 0,
    joins_count          INT UNSIGNED NOT NULL DEFAULT 1,
    display_name         VARCHAR(128) DEFAULT NULL,     -- snapshot on first join
    avatar_url           VARCHAR(255) DEFAULT NULL,     -- snapshot on first join
    UNIQUE KEY uq_call_user (call_id, user_id),
    KEY idx_cp_call (call_id),
    KEY idx_cp_user_first (user_id, first_joined_at),
    CONSTRAINT fk_cp_call FOREIGN KEY (call_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    CONSTRAINT fk_cp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Recording entries per call (multiple recording sessions per call)
CREATE TABLE IF NOT EXISTS call_recordings (
    id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id        BIGINT UNSIGNED NOT NULL,
    file_name      VARCHAR(512) NOT NULL,           -- final file name (with extension), no URL
    started_at     DATETIME NOT NULL,
    ended_at       DATETIME NOT NULL,
    duration_sec   INT UNSIGNED DEFAULT NULL,
    format         ENUM('mp4','webm') NOT NULL DEFAULT 'mp4',
    size_bytes     BIGINT UNSIGNED DEFAULT NULL,
    sent_to_bot    TINYINT(1) NOT NULL DEFAULT 0,
    base_name      VARCHAR(128) DEFAULT NULL,       -- base name used by server (room_owner_ts)
    KEY idx_rec_call (call_id),
    KEY idx_rec_started (started_at),
    CONSTRAINT fk_cr_call FOREIGN KEY (call_id) REFERENCES call_logs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Optional event journal for diagnostics and analytics
CREATE TABLE IF NOT EXISTS call_events (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    call_id      BIGINT UNSIGNED NOT NULL,
    user_id      BIGINT UNSIGNED DEFAULT NULL,     -- actor if present (FK to users.id)
    event_type   ENUM(
                    'owner_join',
                    'peer_join',
                    'peer_leave',
                    'owner_leave',
                    'record_start',
                    'record_pause',
                    'record_resume',
                    'record_stop',
                    'call_status_change',
                    'error'
                 ) NOT NULL,
    payload      JSON DEFAULT NULL,                -- arbitrary event details
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ce_call_time (call_id, created_at),
    CONSTRAINT fk_ce_call FOREIGN KEY (call_id) REFERENCES call_logs(id) ON DELETE CASCADE,
    CONSTRAINT fk_ce_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Unimplemented for now: group chats, conferences, callouts..
CREATE TABLE IF NOT EXISTS rooms (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    room_uid     VARCHAR(64) NOT NULL UNIQUE,
    owner_id     BIGINT UNSIGNED NOT NULL,
    type         ENUM('direct','group') DEFAULT 'direct',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    settings     TEXT,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS room_members (
    room_id      BIGINT UNSIGNED NOT NULL,
    user_id      BIGINT UNSIGNED NOT NULL,
    joined_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (room_id, user_id),
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Indexes (compat: keep also explicit CREATE INDEX with IF NOT EXISTS)

CREATE INDEX IF NOT EXISTS idx_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_tg_user_id ON users(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_room_uid ON rooms(room_uid);