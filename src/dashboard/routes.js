import { listAliveContexts, getAliveContext } from '../browser/contexts.js';
import { getLogsByContext } from '../db/index.js';
import { getContext } from '../db/index.js';

export default async function dashboardRoutes(app) {
  // Summary page
  app.get('/summary', async (req, reply) => {
    const contexts = listAliveContexts();
    return reply.viewAsync('summary.eta', { title: 'Summary', contexts });
  });

  // Live context view
  app.get('/context/:id', async (req, reply) => {
    const entry = getAliveContext(req.params.id);
    if (!entry) {
      const dbCtx = getContext(req.params.id);
      if (dbCtx) {
        return reply.viewAsync('context.eta', {
          title: dbCtx.name,
          context: { ...dbCtx, alive: false },
        });
      }
      return reply.code(404).send('Context not found');
    }
    return reply.viewAsync('context.eta', {
      title: entry.meta.name,
      context: { ...entry.meta, alive: true },
    });
  });

  // Log viewer
  app.get('/logs/:id', async (req, reply) => {
    const entry = getAliveContext(req.params.id);
    const dbCtx = getContext(req.params.id);
    const name = entry?.meta?.name || dbCtx?.name || req.params.id;
    const logs = getLogsByContext(req.params.id);
    return reply.viewAsync('logs.eta', {
      title: `Logs — ${name}`,
      contextId: req.params.id,
      contextName: name,
      logs: logs.reverse(),
    });
  });

  // Redirect root to summary
  app.get('/', async (req, reply) => {
    reply.redirect('/summary');
  });
}
