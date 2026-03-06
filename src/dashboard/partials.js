import { listAliveContexts } from '../browser/contexts.js';

export default async function partialRoutes(app) {
  // Returns the context grid HTML for HTMX swaps
  app.get('/partials/context-list', async (req, reply) => {
    const contexts = listAliveContexts();
    if (contexts.length === 0) {
      return reply.type('text/html').send(`
        <div class="empty-state">
          <p>No active browser contexts.</p>
          <p style="margin-top: 0.5rem; font-size: 0.85rem;">
            Create one via the API: <code>POST /api/contexts</code>
          </p>
        </div>
      `);
    }
    const html = '<div class="grid">'
      + await Promise.all(contexts.map(ctx =>
          reply.viewAsync('partials/context-card.eta', { ctx })
        )).then(parts => parts.join(''))
      + '</div>';
    reply.type('text/html').send(html);
  });
}
