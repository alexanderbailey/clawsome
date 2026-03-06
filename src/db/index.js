import Database from 'better-sqlite3';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

let db;

export function initDb(dbPath) {
  db = new Database(dbPath);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  const schema = readFileSync(join(__dirname, 'schema.sql'), 'utf-8');
  db.exec(schema);

  return db;
}

export function getDb() {
  if (!db) throw new Error('Database not initialised — call initDb() first');
  return db;
}

// --- Context queries ---

export function insertContext({ id, name, profile, visible }) {
  return getDb()
    .prepare('INSERT INTO contexts (id, name, profile, visible) VALUES (?, ?, ?, ?)')
    .run(id, name, profile ?? null, visible ? 1 : 0);
}

export function listContexts() {
  return getDb()
    .prepare('SELECT * FROM contexts ORDER BY created_at DESC')
    .all();
}

export function getContext(id) {
  return getDb()
    .prepare('SELECT * FROM contexts WHERE id = ?')
    .get(id);
}

export function updateContextStatus(id, status) {
  return getDb()
    .prepare('UPDATE contexts SET status = ?, updated_at = datetime(\'now\') WHERE id = ?')
    .run(status, id);
}

export function deleteContext(id) {
  return getDb()
    .prepare('DELETE FROM contexts WHERE id = ?')
    .run(id);
}

// --- Log queries ---

export function insertLog({ contextId, level, message }) {
  return getDb()
    .prepare('INSERT INTO logs (context_id, level, message) VALUES (?, ?, ?)')
    .run(contextId, level ?? 'info', message);
}

export function getLogsByContext(contextId, limit = 200) {
  return getDb()
    .prepare('SELECT * FROM logs WHERE context_id = ? ORDER BY created_at DESC LIMIT ?')
    .all(contextId, limit);
}
