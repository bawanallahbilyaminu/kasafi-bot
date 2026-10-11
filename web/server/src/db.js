// Chat history and profiles (SQLite). One file, no separate database server to run on the VPS.
import Database from 'better-sqlite3'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'

const file = process.env.DB_PATH || './data/kasafi-web.sqlite'
fs.mkdirSync(path.dirname(file), { recursive: true })
const db = new Database(file)
db.pragma('journal_mode = WAL')
db.pragma('foreign_keys = ON')
db.exec(`
CREATE TABLE IF NOT EXISTS profiles (
  user_id TEXT PRIMARY KEY, name TEXT NOT NULL, organization TEXT NOT NULL, email TEXT,
  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT 'Sabuwar tattaunawa',
  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user','assistant')), content TEXT NOT NULL, input_type TEXT DEFAULT 'text',
  transcript TEXT, interaction_id INTEGER, lang TEXT, voice INTEGER DEFAULT 0, feedback INTEGER,
  created_at TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id);
`)

export const profiles = {
  get: (userId) => db.prepare('SELECT name, organization, email FROM profiles WHERE user_id=?').get(userId) || null,
  upsert: (userId, { name, organization, email }) =>
    db.prepare(`INSERT INTO profiles (user_id, name, organization, email) VALUES (?, ?, ?, ?)
      ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, organization=excluded.organization,
      email=coalesce(excluded.email, profiles.email), updated_at=datetime('now')`).run(userId, name, organization, email || null),
}

export const sessions = {
  list: (userId) => db.prepare(`SELECT id, title, created_at, updated_at FROM sessions WHERE user_id=?
      ORDER BY updated_at DESC LIMIT 200`).all(userId),
  get: (userId, id) => db.prepare('SELECT id, title, created_at, updated_at FROM sessions WHERE user_id=? AND id=?').get(userId, id),
  create: (userId, title) => {
    const id = crypto.randomUUID()
    db.prepare('INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)').run(id, userId, title || 'Sabuwar tattaunawa')
    return sessions.get(userId, id)
  },
  rename: (userId, id, title) =>
    db.prepare(`UPDATE sessions SET title=?, updated_at=datetime('now') WHERE user_id=? AND id=?`).run(title, userId, id).changes,
  touch: (id) => db.prepare(`UPDATE sessions SET updated_at=datetime('now') WHERE id=?`).run(id),
  remove: (userId, id) => db.prepare('DELETE FROM sessions WHERE user_id=? AND id=?').run(userId, id).changes,
}

export const messages = {
  list: (sessionId) => db.prepare(`SELECT id, role, content, input_type, transcript, interaction_id, lang, voice, feedback,
      created_at FROM messages WHERE session_id=? ORDER BY id`).all(sessionId),
  add: (sessionId, m) => {
    const r = db.prepare(`INSERT INTO messages (session_id, role, content, input_type, transcript, interaction_id, lang, voice)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`).run(sessionId, m.role, m.content, m.input_type || 'text', m.transcript || null,
      m.interaction_id || null, m.lang || null, m.voice ? 1 : 0)
    sessions.touch(sessionId)
    return db.prepare('SELECT * FROM messages WHERE id=?').get(r.lastInsertRowid)
  },
  update: (id, fields) => {
    const keys = Object.keys(fields)
    db.prepare(`UPDATE messages SET ${keys.map((k) => `${k}=?`).join(', ')} WHERE id=?`).run(...keys.map((k) => fields[k]), id)
  },
  owned: (userId, id) => db.prepare(`SELECT m.* FROM messages m JOIN sessions s ON s.id=m.session_id
      WHERE m.id=? AND s.user_id=?`).get(id, userId),
}

export default db
