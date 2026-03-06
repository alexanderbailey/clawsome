import Fastify from 'fastify';
import fastifyView from '@fastify/view';
import fastifyStatic from '@fastify/static';
import { Eta } from 'eta';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { mkdirSync } from 'fs';
import { initDb } from './db/index.js';
import { launchBrowser, closeBrowser } from './browser/manager.js';
import { destroyAllContexts } from './browser/contexts.js';
import contextRoutes from './api/contexts.js';
import dashboardRoutes from './dashboard/routes.js';
import partialRoutes from './dashboard/partials.js';
import sseRoutes from './dashboard/sse.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');

const PORT = parseInt(process.env.PORT || '3000', 10);
const HOST = process.env.HOST || '0.0.0.0';

// Ensure data directory exists
mkdirSync(join(ROOT, 'data'), { recursive: true });

// Init database
initDb(join(ROOT, 'data', 'clawsome.db'));

// Create Fastify instance
const app = Fastify({ logger: true });

// Template engine
const eta = new Eta({ views: join(__dirname, 'views'), cache: true });
await app.register(fastifyView, {
  engine: { eta },
  root: join(__dirname, 'views'),
});

// Static files
await app.register(fastifyStatic, {
  root: join(__dirname, 'public'),
  prefix: '/public/',
});

// Health check
app.get('/health', async () => ({ status: 'ok' }));

// Routes
await app.register(contextRoutes);
await app.register(dashboardRoutes);
await app.register(partialRoutes);
await app.register(sseRoutes);

// Launch browser + start server
try {
  await launchBrowser();
  app.log.info('Playwright browser launched');
  await app.listen({ port: PORT, host: HOST });
} catch (err) {
  app.log.error(err);
  process.exit(1);
}

// Graceful shutdown
async function shutdown() {
  app.log.info('Shutting down...');
  await destroyAllContexts();
  await closeBrowser();
  await app.close();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
