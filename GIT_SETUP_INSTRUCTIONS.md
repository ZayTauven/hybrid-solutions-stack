# Hybrid Solutions Stack - Git Setup Instructions

**For:** Zay  
**Date:** 2026-09-20  
**Status:** Ready to clone into your repos

---

## 📦 What You Have

Two files to download from `/mnt/user-data/outputs/`:

1. **`hybrid-stack-complete.tar.gz`** (33 KB)
   - Complete stack with all 9 skills, 6 agents, 6 templates
   - Documentation (README, DEPLOY_GUIDE, INDEX, stack.yml)

2. **`SETUP.sh`** (Setup script)
   - Automates local installation
   - Checks prerequisites
   - Starts Docker services
   - Shows access points

---

## 🚀 Quick Start (3 Steps)

### Step 1: Extract Archive

```bash
# Download hybrid-stack-complete.tar.gz

# Extract
tar -xzf hybrid-stack-complete.tar.gz

# Navigate
cd hybrid-stack
```

### Step 2: Run Setup Script

```bash
# Make script executable
chmod +x ../SETUP.sh

# Run setup
../SETUP.sh

# Or manually:
docker-compose -f templates/docker-compose/docker-compose.yml up -d
```

### Step 3: Access & Test

```bash
# Frontend
open http://localhost:3000

# API
curl http://localhost:8000/api/health/

# Database
psql -U appuser -d shared_meta -h localhost
```

---

## 📂 Your Repository Structure (After Clone)

```
your-repo/
├── hybrid-stack/                    # Extracted from archive
│   ├── skills/                      (9 skills)
│   ├── agents/                      (6 agents)
│   ├── templates/                   (code starters)
│   ├── README.md
│   ├── DEPLOY_GUIDE.md
│   ├── INDEX.md
│   ├── stack.yml
│   └── ...
│
├── SETUP.sh                         # Setup script
├── .gitignore                       # Use provided template
└── README.md                        # Your project README
```

---

## 🔧 Option 1: Simple Clone (Recommended)

```bash
# Your personal repo
git clone https://github.com/your-username/your-repo.git
cd your-repo

# Extract archive
tar -xzf hybrid-stack-complete.tar.gz

# Initialize git in hybrid-stack (if separate repo)
cd hybrid-stack
git init
git add .
git commit -m "Initial: hybrid-stack v1.0"
git remote add origin https://github.com/your-username/hybrid-solutions-stack.git
git push -u origin main
```

---

## 🔧 Option 2: Submodule (If Multiple Repos)

```bash
# Your main repo
git clone https://github.com/your-username/my-projects.git
cd my-projects

# Add as submodule
git submodule add https://github.com/your-username/hybrid-stack.git

# Commit
git add .gitmodules hybrid-stack/
git commit -m "Add hybrid-stack as submodule"
git push
```

---

## 🔧 Option 3: Monorepo (If You Want Everything Together)

```bash
# Structure
my-monorepo/
├── projects/
│   ├── hybrid-solutions-stack/      (the stack)
│   ├── client-project-1/            (uses the stack)
│   ├── client-project-2/            (uses the stack)
│   └── ...
├── docs/
├── shared/
└── .github/workflows/               (CI/CD)
```

---

## 📋 .gitignore (Recommended)

Create in root of repo:

```
# Dependencies
node_modules/
*.egg-info/
__pycache__/
.venv/
venv/

# Environment
.env
.env.local
.env.*.local

# Docker
docker-compose.override.yml
.dockerignore

# Logs
logs/
*.log
npm-debug.log*

# OS
.DS_Store
.vscode/
.idea/

# Data
backups/
postgres_data/
redis_data/

# Temp
*.tmp
.cache/
dist/
build/
```

---

## 🚀 Local Installation Checklist

- [ ] Download `hybrid-stack-complete.tar.gz`
- [ ] Download `SETUP.sh`
- [ ] Extract archive: `tar -xzf hybrid-stack-complete.tar.gz`
- [ ] Make script executable: `chmod +x SETUP.sh`
- [ ] Run setup: `./SETUP.sh`
- [ ] Wait for services to start (~30 seconds)
- [ ] Test frontend: `http://localhost:3000`
- [ ] Test API: `curl http://localhost:8000/api/health/`
- [ ] Read `README.md` for overview
- [ ] Pick an agent based on your need
- [ ] Follow `DEPLOY_GUIDE.md` for next steps

---

## 📖 Documentation in Order

1. **README.md** (15 min) - Overview & quick start
2. **stack.yml** (30 min) - Architecture definition
3. **Pick Agent** (5 min) - Choose your path
4. **Agent Guide** (30 min) - `/agents/*/agent.md`
5. **Skill Deep Dive** (2-4 hours) - Read relevant SKILL.md files
6. **DEPLOY_GUIDE.md** - Step-by-step deployment

---

## 💻 Commands Reference

### Start Stack

```bash
docker-compose -f templates/docker-compose/docker-compose.yml up -d
```

### Stop Stack

```bash
docker-compose -f templates/docker-compose/docker-compose.yml down
```

### View Logs

```bash
docker-compose -f templates/docker-compose/docker-compose.yml logs -f
docker-compose -f templates/docker-compose/docker-compose.yml logs -f django
docker-compose -f templates/docker-compose/docker-compose.yml logs -f postgres
```

### Database Access

```bash
# Via Docker
docker-compose -f templates/docker-compose/docker-compose.yml exec postgres psql -U appuser -d shared_meta

# Via CLI
psql -U appuser -d shared_meta -h localhost -p 5432
# Password: (from .env DB_PASSWORD)
```

### Test API Sync

```bash
curl -X POST http://localhost:8000/api/sync \
  -H "Content-Type: application/json" \
  -H "X-Tenant: tenant_cmr_001" \
  -d '{"events": []}'
```

---

## 🆘 Troubleshooting

### Docker not found
```bash
# Install Docker
# macOS: brew install docker
# Ubuntu: sudo apt install docker.io
# Windows: Download Docker Desktop
```

### Port 3000/8000 already in use
```bash
# Find process using port
lsof -i :3000

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

### Database connection refused
```bash
# Wait for database to start
sleep 30

# Check logs
docker-compose logs postgres

# Reset database
docker-compose down -v  # WARNING: Deletes data!
docker-compose up -d
```

### Services not starting
```bash
# Check Docker
docker --version

# Check Compose
docker-compose --version

# Rebuild containers
docker-compose build --no-cache
docker-compose up -d
```

---

## 📊 What to Expect

After running `./SETUP.sh`:

- ✅ PostgreSQL database running
- ✅ Redis cache running
- ✅ Django API running on port 8000
- ✅ NextJS frontend running on port 3000
- ✅ Celery worker running
- ✅ All ready for development

---

## 🎯 Next Steps After Setup

1. **Explore the stack**
   - Check `/skills/sync-engine-setup/SKILL.md`
   - Test offline mode in browser

2. **Pick your use case**
   - ERP? → `/agents/bootstrap-hybrid-erp/`
   - Project Mgmt? → `/agents/bootstrap-project-mgmt/`
   - CRM? → `/agents/bootstrap-crm/`

3. **Start building**
   - Copy templates
   - Customize for your domain
   - Deploy to server

4. **Share your improvements**
   - Push back to repo
   - Document what you learn
   - Create new agents for your needs

---

## 📞 Support

All documentation is self-contained:
- `README.md` - Overview
- `DEPLOY_GUIDE.md` - Deployment
- `INDEX.md` - Complete inventory
- `stack.yml` - Architecture
- `/skills/*/SKILL.md` - Detailed guides (9 files)
- `/agents/*/agent.md` - Workflow guides (6 files)

---

**Status:** ✅ Ready to clone  
**Version:** 1.0  
**Size:** 33 KB (compressed)

Good luck! 🚀
