# Skill: PostgreSQL Backup Strategy (3-2-1)

**Purpose:** Implement 3 copies, 2 formats, 1 offsite backup strategy

---

## 3-2-1 Backup Rule

```
3 Copies:
├── Copy 1: Local daily backup (7 days retention)
├── Copy 2: Local weekly backup (4 weeks retention)
└── Copy 3: S3 cloud backup (12 months retention)

2 Formats:
├── Format 1: Full database dump (pg_dump)
└── Format 2: WAL archiving (incremental)

1 Offsite:
└── AWS S3 in different region
```

---

## Backup Script

```python
# management/commands/backup_databases.py
import subprocess
import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from datetime import datetime, timedelta

class Command(BaseCommand):
    def handle(self, *args, **options):
        # 1. Local backup
        self.backup_local()
        
        # 2. Upload to S3
        self.upload_to_s3()
        
        # 3. Cleanup old backups
        self.cleanup_old_backups()
    
    def backup_local(self):
        """Create local PostgreSQL dump"""
        backup_dir = '/backups/daily'
        filename = f"{backup_dir}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql.gz"
        
        cmd = [
            'pg_dump',
            settings.DATABASES['default']['NAME'],
            '--compress=9',
            '--file=' + filename
        ]
        
        subprocess.run(cmd, check=True)
        self.stdout.write(f"Backup created: {filename}")
    
    def upload_to_s3(self):
        """Upload backup to AWS S3"""
        s3 = boto3.client('s3')
        backup_file = self.get_latest_backup()
        
        s3.upload_file(
            backup_file,
            'backups-comores',
            f"postgresql/daily/{backup_file.split('/')[-1]}",
            ServerSideEncryption='AES256'
        )
        
        self.stdout.write("Uploaded to S3")
    
    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        cutoff = datetime.now() - timedelta(days=7)
        # Remove files older than 7 days
```

---

## Restore from Backup

```bash
# Restore from dump
pg_restore -d app_cmr_001 backup_20240101.sql

# Verify restore
psql -d app_cmr_001 -c "SELECT COUNT(*) FROM invoices;"
```

---

## WAL Archiving (Point-in-Time Recovery)

```sql
-- postgresql.conf
wal_level = replica
max_wal_senders = 3
wal_keep_size = '1GB'
archive_mode = on
archive_command = 'test ! -f /mnt/server/wal_archive/%f && cp %p /mnt/server/wal_archive/%f'
```

---

## Backup Verification

```python
def verify_backup(backup_file):
    """Test restore without actually restoring"""
    result = subprocess.run([
        'pg_restore',
        '--list',
        backup_file
    ], capture_output=True)
    
    return result.returncode == 0
```

