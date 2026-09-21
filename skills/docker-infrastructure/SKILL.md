# Skill: Docker Infrastructure Setup

**Purpose:** Production-ready Docker compose for local + central deployment

---

## docker-compose.yml (Local Site)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: app_cmr_001
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - app

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - app

  django:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: python manage.py runserver 0.0.0.0:8000
    environment:
      DATABASE_URL: postgresql://appuser:${DB_PASSWORD}@postgres:5432/app_cmr_001
      REDIS_URL: redis://redis:6379
      DEBUG: ${DEBUG:-false}
      TENANT_MODE: local
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./backend:/app
    networks:
      - app

  celery:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A myapp worker -l info
    environment:
      DATABASE_URL: postgresql://appuser:${DB_PASSWORD}@postgres:5432/app_cmr_001
      REDIS_URL: redis://redis:6379
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app
    networks:
      - app

  nextjs:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    command: npm run dev
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - django
    volumes:
      - ./frontend:/app
      - /app/node_modules
    networks:
      - app

volumes:
  postgres_data:
  redis_data:

networks:
  app:
    driver: bridge
```

---

## Dockerfile (Django)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y postgresql-client

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "myapp.wsgi"]
```

---

## .env Template

```
DB_PASSWORD=your_secure_password
DEBUG=false
SECRET_KEY=your-secret-key
TENANT_MODE=local  # or 'central'
SYNC_CONFLICT_RESOLUTION=last-write-wins
```

---

## Health Checks

```python
# views.py
@api_view(['GET'])
def health_check(request):
    return Response({
        'status': 'ok',
        'database': check_db(),
        'redis': check_redis(),
        'timestamp': timezone.now(),
    })

def check_db():
    try:
        connection.ensure_connection()
        return 'connected'
    except:
        return 'disconnected'
```

