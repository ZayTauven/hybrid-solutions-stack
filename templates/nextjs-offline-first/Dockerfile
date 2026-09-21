FROM node:22-alpine

WORKDIR /app

# Dependencies live in the image; the source is bind-mounted in development.
# node_modules is masked by an anonymous volume in docker-compose.yml so the
# host's (possibly absent, possibly Windows-built) copy never shadows this one.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
