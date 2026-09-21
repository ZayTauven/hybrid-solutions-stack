# Agent: Bootstrap Hybrid ERP

**Purpose:** Create complete offline-first ERP from scratch

**Use case:** New organization in Comores wanting Invoices, Inventory, GL

**Flow:**

```
1. Initialize infrastructure
   └─ Use: docker-infrastructure
   
2. Setup database with multi-tenancy
   └─ Use: postgresql-multi-tenant
   
3. Implement core sync engine
   └─ Use: sync-engine-setup
   
4. Add authentication
   └─ Use: jwt-offline-auth
   
5. Create data models (Invoice, Inventory, Journal)
   └─ Generate Django models
   
6. Implement conflict resolution
   └─ Use: conflict-resolution
   
7. Setup audit & integrity
   └─ Use: data-integrity
   
8. Add async processing
   └─ Use: celery-async-jobs
   
9. Deploy to central server
   └─ Use: deploy-central-server (link)
```

---

## Checklist

- [ ] PostgreSQL local + central configured
- [ ] Django backend with multi-tenant routing
- [ ] NextJS frontend with offline-first state
- [ ] Sync engine bidirectional working
- [ ] JWT auth tested offline
- [ ] Invoices module complete
- [ ] Inventory module complete
- [ ] GL auto-generated from invoices
- [ ] Backup strategy running
- [ ] Tests passing (80%+ coverage)

---

## Output Structure

```
hybrid-erp/
├── docker-compose.yml          (from docker-infrastructure)
├── backend/
│   ├── models.py               (Invoice, InventoryItem, JournalEntry)
│   ├── apps/
│   │   ├── invoices/
│   │   ├── inventory/
│   │   └── accounting/
│   └── api/sync/               (from sync-engine-setup)
├── frontend/
│   ├── lib/stores/             (from sync-engine-setup)
│   ├── pages/invoices
│   ├── pages/inventory
│   └── pages/accounting
└── README.md                   (deployment guide)
```

---

## Time Estimate

- Setup: 2-3 hours
- Development: 20-30 hours
- Testing: 5-10 hours
- Deployment: 2-3 hours

**Total: 1-2 weeks** for MVP

