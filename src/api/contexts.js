import {
  createContext,
  getAliveContext,
  listAliveContexts,
  navigateTo,
  takeScreenshot,
  execAction,
  destroyContext,
} from '../browser/contexts.js';
import { insertLog, getLogsByContext } from '../db/index.js';
import { broadcast } from '../dashboard/sse.js';

export default async function contextRoutes(app) {
  // List all contexts
  app.get('/api/contexts', async () => {
    return listAliveContexts();
  });

  // Create a context
  app.post('/api/contexts', async (req, reply) => {
    const { name, profile, visible } = req.body || {};
    if (!name) return reply.code(400).send({ error: 'name is required' });

    const meta = await createContext({ name, profile, visible });
    insertLog({ contextId: meta.id, level: 'info', message: `Context created: ${name}` });
    broadcast({ event: 'context:created', data: meta });
    reply.code(201).send(meta);
  });

  // Get a single context
  app.get('/api/contexts/:id', async (req, reply) => {
    const entry = getAliveContext(req.params.id);
    if (!entry) return reply.code(404).send({ error: 'Context not found' });
    return entry.meta;
  });

  // Destroy a context
  app.delete('/api/contexts/:id', async (req, reply) => {
    const { id } = req.params;
    try {
      await destroyContext(id);
      insertLog({ contextId: id, level: 'info', message: 'Context destroyed' });
      broadcast({ event: 'context:destroyed', data: { id } });
      return { ok: true };
    } catch (err) {
      return reply.code(404).send({ error: err.message });
    }
  });

  // Navigate to a URL
  app.post('/api/contexts/:id/goto', async (req, reply) => {
    const { url } = req.body || {};
    if (!url) return reply.code(400).send({ error: 'url is required' });

    try {
      const result = await navigateTo(req.params.id, url);
      insertLog({ contextId: req.params.id, level: 'info', message: `Navigated to ${url}` });
      broadcast({ event: 'context:updated', data: { id: req.params.id, url } });
      return result;
    } catch (err) {
      return reply.code(404).send({ error: err.message });
    }
  });

  // Take a screenshot
  app.get('/api/contexts/:id/screenshot', async (req, reply) => {
    try {
      const buffer = await takeScreenshot(req.params.id);
      reply.type('image/png').send(buffer);
    } catch (err) {
      reply.code(404).send({ error: err.message });
    }
  });

  // Execute an action
  app.post('/api/contexts/:id/exec', async (req, reply) => {
    const { action, selector, value, script } = req.body || {};
    if (!action) return reply.code(400).send({ error: 'action is required' });

    try {
      const result = await execAction(req.params.id, { action, selector, value, script });
      insertLog({ contextId: req.params.id, level: 'info', message: `Executed: ${action} ${selector || ''}`.trim() });
      return result;
    } catch (err) {
      return reply.code(400).send({ error: err.message });
    }
  });

  // Get logs for a context
  app.get('/api/contexts/:id/logs', async (req, reply) => {
    try {
      const logs = getLogsByContext(req.params.id);
      return logs;
    } catch (err) {
      return reply.code(404).send({ error: err.message });
    }
  });

  // Append a log entry
  app.post('/api/contexts/:id/logs', async (req, reply) => {
    const { level, message } = req.body || {};
    if (!message) return reply.code(400).send({ error: 'message is required' });

    insertLog({ contextId: req.params.id, level: level || 'info', message });
    broadcast({ event: 'log:new', data: { contextId: req.params.id, level, message } });
    reply.code(201).send({ ok: true });
  });
}
