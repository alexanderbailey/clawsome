import Fastify from 'fastify';
import fastifyView from '@fastify/view';
import fastifyStatic from '@fastify/static';
import { Eta } from 'eta';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { mkdirSync } from 'fs';
import { initDb } from './db/index.js';

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

// Start
try {
  await app.listen({ port: PORT, host: HOST });
} catch (err) {
  app.log.error(err);
  process.exit(1);
}
