-- All users that are seen by bot
CREATE TABLE users (
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
CREATE TABLE user_contacts (
    user_id     BIGINT UNSIGNED NOT NULL,       -- who has been add
    contact_id  BIGINT UNSIGNED NOT NULL,       -- whom
    is_friend   BOOLEAN DEFAULT FALSE,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, contact_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE user_blacklist (
    user_id     BIGINT UNSIGNED NOT NULL,      -- who blocks
    blocked_id  BIGINT UNSIGNED NOT NULL,      -- who is blocked
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, blocked_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (blocked_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE invites (
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


CREATE TABLE call_logs (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id      BIGINT UNSIGNED NOT NULL,
    peer_id      BIGINT UNSIGNED NOT NULL,
    started_at   DATETIME,
    ended_at     DATETIME,
    duration     INT UNSIGNED,
    type         ENUM('audio','video') DEFAULT 'video',
    status       ENUM('success','missed','failed') DEFAULT 'success',
    metadata     TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (peer_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Unimplemented for now: group chats, conferences, callouts..
CREATE TABLE rooms (
    id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    room_uid     VARCHAR(64) NOT NULL UNIQUE,
    owner_id     BIGINT UNSIGNED NOT NULL,
    type         ENUM('direct','group') DEFAULT 'direct',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    settings     TEXT,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE room_members (
    room_id      BIGINT UNSIGNED NOT NULL,
    user_id      BIGINT UNSIGNED NOT NULL,
    joined_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (room_id, user_id),
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE INDEX idx_username ON users(username);
CREATE INDEX idx_tg_user_id ON users(tg_user_id);
CREATE INDEX idx_room_uid ON rooms(room_uid);
