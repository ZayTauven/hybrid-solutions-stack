import fs from 'node:fs';
import path from 'node:path';

import {
  copyTree,
  keepOnly,
  patchFile,
  prune,
  readJson,
  writeJson,
} from './fs-utils.js';
import { resolveSource } from './skin.js';

/**
 * Substitute the project's identity into overlay files.
 *
 * Overlay files are written as ordinary source with `{{TOKENS}}` where the
 * generated identity belongs, so they stay readable and lint-able in place.
 */
function render(text, tokens) {
  return text.replace(/\{\{(\w+)\}\}/g, (match, key) =>
    key in tokens ? String(tokens[key]) : match,
  );
}

const TEXT_EXTENSIONS = new Set([
  '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
  '.json', '.css', '.scss', '.md', '.html', '.env', '.yml', '.yaml',
]);

function copyOverlay(overlayDir, targetDir, tokens) {
  if (!fs.existsSync(overlayDir)) return 0;
  let written = 0;

  function walk(src, dest) {
    for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
      const srcPath = path.join(src, entry.name);
      const destPath = path.join(dest, entry.name);

      if (entry.isDirectory()) {
        fs.mkdirSync(destPath, { recursive: true });
        walk(srcPath, destPath);
        continue;
      }

      fs.mkdirSync(path.dirname(destPath), { recursive: true });

      if (TEXT_EXTENSIONS.has(path.extname(entry.name))) {
        fs.writeFileSync(destPath, render(fs.readFileSync(srcPath, 'utf8'), tokens), 'utf8');
      } else {
        fs.copyFileSync(srcPath, destPath);
      }
      written += 1;
    }
  }

  walk(overlayDir, targetDir);
  return written;
}

export function assembleFrontend({ repoRoot, skin, identity, projectName, targetDir }) {
  const sourceDir = resolveSource(repoRoot, skin);
  const frontendDir = path.join(targetDir, 'frontend');

  // A vendored skin is its own source, so the adapter's own files sit in the
  // same directory as the application's and must not be copied into it.
  const copied = copyTree(sourceDir, frontendDir, {
    skip: ['skin.json', 'overlay', 'README.md'],
  });
  const report = { copied, pruned: 0, kept: [], overlay: 0, warnings: [] };

  // Keep-lists first: they are how hundreds of demo screens go away.
  for (const [dir, keep] of Object.entries(skin.keepOnly ?? {})) {
    const result = keepOnly(path.join(frontendDir, dir), keep);
    report.pruned += result.removed;
    if (result.missing.length) {
      report.warnings.push(
        `keepOnly(${dir}): expected but absent -> ${result.missing.join(', ')}`,
      );
    }
  }

  const pruneResult = prune(frontendDir, skin.prune ?? []);
  report.pruned += pruneResult.removed;
  if (pruneResult.missing.length) {
    report.warnings.push(
      `prune: already absent -> ${pruneResult.missing.join(', ')}`,
    );
  }

  const tokens = {
    PROJECT_NAME: projectName,
    PRIMARY: identity.palette.primary,
    SECONDARY: identity.palette.secondary,
    PRIMARY_DARK: identity.palette.primaryDark,
    SECONDARY_DARK: identity.palette.secondaryDark,
    PALETTE_ID: identity.palette.id,
    RADIUS: identity.shape.radius,
    DENSITY: identity.shape.density,
    LAYOUT: identity.layout ?? '',
  };

  report.overlay = copyOverlay(path.join(skin.dir, 'overlay'), frontendDir, tokens);

  for (const patch of skin.patches ?? []) {
    patchFile(path.join(frontendDir, patch.file), patch.replacements.map((r) => ({
      ...r,
      replace: render(r.replace, tokens),
    })));
  }

  applyFrontendManifest({ frontendDir, skin, projectName });

  return report;
}

/**
 * Merge the skin's requirements into the template's own package.json.
 *
 * Rewriting it wholesale would drop whatever the template genuinely needs;
 * merging keeps its dependencies and adds ours on top.
 */
function applyFrontendManifest({ frontendDir, skin, projectName }) {
  const manifestPath = path.join(frontendDir, 'package.json');
  const manifest = readJson(manifestPath);

  manifest.name = `@${projectName}/frontend`;
  manifest.private = true;
  // The template's own licence does not travel to the generated project: the
  // licence is yours, held outside the code.
  delete manifest.license;

  manifest.dependencies = {
    ...manifest.dependencies,
    ...(skin.dependencies ?? {}),
  };

  for (const name of skin.removeDependencies ?? []) {
    delete manifest.dependencies?.[name];
    delete manifest.devDependencies?.[name];
  }

  manifest.scripts = {
    ...manifest.scripts,
    typecheck: 'tsc --noEmit',
  };

  writeJson(manifestPath, manifest);
}

export function assembleBackend({ repoRoot, targetDir }) {
  const from = path.join(repoRoot, 'templates', 'django-api-sync');
  const to = path.join(targetDir, 'backend');
  return copyTree(from, to, { skip: ['staticfiles', '__pycache__'] });
}

export function assembleCore({ repoRoot, targetDir }) {
  const from = path.join(repoRoot, 'packages', 'offline-core');
  const to = path.join(targetDir, 'packages', 'offline-core');
  return copyTree(from, to);
}

export function assembleInfra({ repoRoot, targetDir, projectName, ports, secrets }) {
  const dockerDir = path.join(targetDir, 'docker');
  fs.mkdirSync(dockerDir, { recursive: true });

  copyTree(
    path.join(repoRoot, 'templates', 'postgresql-schema'),
    path.join(dockerDir, 'postgresql'),
  );

  fs.writeFileSync(
    path.join(dockerDir, 'docker-compose.yml'),
    composeFile(projectName),
    'utf8',
  );

  fs.writeFileSync(path.join(targetDir, '.env'), envFile(ports, secrets), 'utf8');
  fs.writeFileSync(
    path.join(targetDir, '.env.example'),
    envFile({ postgres: 5432, redis: 6379, django: 8000, next: 3000 }, {
      dbPassword: 'change-me',
      appDbPassword: 'change-me-too',
      secretKey: 'change-me-in-production',
      jwtKey: 'change-me-in-production',
    }),
    'utf8',
  );

  writeJson(path.join(targetDir, 'package.json'), {
    name: projectName,
    version: '0.1.0',
    private: true,
    workspaces: ['packages/*', 'frontend'],
    scripts: {
      typecheck: 'npm run typecheck --workspaces --if-present',
    },
  });

  fs.writeFileSync(path.join(targetDir, '.gitignore'), gitignoreFile(), 'utf8');
  fs.writeFileSync(path.join(targetDir, '.dockerignore'), dockerignoreFile(), 'utf8');
}

function composeFile(projectName) {
  return `# ${projectName} — generated by create-hybrid-app
#
# First run:
#   docker compose -f docker/docker-compose.yml --env-file .env up -d --build
#   docker compose -f docker/docker-compose.yml exec django python manage.py migrate
#   docker compose -f docker/docker-compose.yml exec django python manage.py seed_demo
#
# Migrations install the tenant isolation policies alongside the tables, so
# there is no manual SQL step and no way to forget it.

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: shared_meta
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: \${DB_PASSWORD}
      APP_DB_PASSWORD: \${APP_DB_PASSWORD}
    ports:
      - "127.0.0.1:\${POSTGRES_HOST_PORT}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./postgresql/01-init-roles.sh:/docker-entrypoint-initdb.d/01-init-roles.sh:ro
      - ./postgresql/init.sql:/docker-entrypoint-initdb.d/02-init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d shared_meta"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks: [hybrid]

  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:\${REDIS_HOST_PORT}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks: [hybrid]

  django:
    build:
      context: ../backend
      dockerfile: Dockerfile
    command: >
      sh -c "python manage.py migrate &&
             python manage.py runserver 0.0.0.0:8000"
    environment:
      DATABASE_URL: postgresql://hybrid_app:\${APP_DB_PASSWORD}@postgres:5432/shared_meta
      REDIS_URL: redis://redis:6379/0
      DEBUG: \${DEBUG:-false}
      SECRET_KEY: \${SECRET_KEY}
      JWT_SECRET_KEY: \${JWT_SECRET_KEY}
      ALLOWED_HOSTS: \${ALLOWED_HOSTS:-localhost,127.0.0.1}
      CORS_ALLOWED_ORIGINS: \${CORS_ALLOWED_ORIGINS:-http://localhost:\${NEXTJS_HOST_PORT}}
    ports:
      - "\${DJANGO_HOST_PORT}:8000"
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes:
      - ../backend:/app
    networks: [hybrid]

  celery:
    build:
      context: ../backend
      dockerfile: Dockerfile
    command: celery -A myapp worker -l info
    environment:
      DATABASE_URL: postgresql://hybrid_app:\${APP_DB_PASSWORD}@postgres:5432/shared_meta
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: \${SECRET_KEY}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes:
      - ../backend:/app
    networks: [hybrid]

  celery-beat:
    build:
      context: ../backend
      dockerfile: Dockerfile
    command: celery -A myapp beat -l info
    environment:
      DATABASE_URL: postgresql://hybrid_app:\${APP_DB_PASSWORD}@postgres:5432/shared_meta
      REDIS_URL: redis://redis:6379/0
      SECRET_KEY: \${SECRET_KEY}
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes:
      - ../backend:/app
    networks: [hybrid]

  nextjs:
    build:
      context: ..
      dockerfile: frontend/Dockerfile
    command: npm run dev
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:\${DJANGO_HOST_PORT}
      NEXT_PUBLIC_SYNC_ORIGIN: \${SYNC_ORIGIN:-web}
    ports:
      - "\${NEXTJS_HOST_PORT}:3000"
    depends_on: [django]
    volumes:
      - ../frontend:/app/frontend
      - ../packages/offline-core:/app/packages/offline-core
      - /app/node_modules
      - /app/frontend/node_modules
    networks: [hybrid]

volumes:
  postgres_data:
  redis_data:

networks:
  hybrid:
    driver: bridge
`;
}

function envFile(ports, secrets) {
  return `# Local configuration. Never commit this file.

DB_PASSWORD=${secrets.dbPassword}
# The application role. RLS policies apply to it; appuser bypasses them.
APP_DB_PASSWORD=${secrets.appDbPassword}

SECRET_KEY=${secrets.secretKey}
JWT_SECRET_KEY=${secrets.jwtKey}
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1

# Host ports, chosen to avoid what was already listening when this was generated.
POSTGRES_HOST_PORT=${ports.postgres}
REDIS_HOST_PORT=${ports.redis}
DJANGO_HOST_PORT=${ports.django}
NEXTJS_HOST_PORT=${ports.next}

CORS_ALLOWED_ORIGINS=http://localhost:${ports.next}
SYNC_ORIGIN=web
`;
}

function gitignoreFile() {
  return `node_modules/
.next/
out/
__pycache__/
*.py[cod]
.venv/
staticfiles/
.env
*.tsbuildinfo
celerybeat-schedule*
.DS_Store
`;
}

function dockerignoreFile() {
  return `node_modules/
**/node_modules/
.next/
**/.next/
.git/
__pycache__/
**/__pycache__/
.env
*.tsbuildinfo
`;
}
