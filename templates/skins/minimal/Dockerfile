# Build context is the repository root, not this directory: the skin depends on
# packages/offline-core through an npm workspace, and a sibling package cannot
# be copied from a context that starts below it.
FROM node:22-alpine

WORKDIR /app

# Manifests first, so a source edit does not invalidate the install layer.
COPY package.json package-lock.json* ./
COPY packages/offline-core/package.json ./packages/offline-core/
COPY templates/skins/minimal/package.json ./templates/skins/minimal/
RUN npm install

COPY packages/offline-core ./packages/offline-core
COPY templates/skins/minimal ./templates/skins/minimal

WORKDIR /app/templates/skins/minimal

EXPOSE 3000

CMD ["npm", "run", "dev"]
