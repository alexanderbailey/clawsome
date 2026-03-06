const clients = new Set();

/**
 * Broadcast an event to all connected SSE clients.
 * @param {{ event: string, data: any }} payload
 */
export function broadcast({ event, data }) {
  const message = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of clients) {
    try {
      res.raw.write(message);
    } catch {
      clients.delete(res);
    }
  }
}

/**
 * Register the SSE endpoint on the Fastify app.
 */
export default async function sseRoutes(app) {
  app.get('/sse/updates', (req, reply) => {
    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    });

    // Send initial ping
    reply.raw.write('event: ping\ndata: {}\n\n');

    clients.add(reply);

    req.raw.on('close', () => {
      clients.delete(reply);
    });
  });
}
