#!/bin/bash

# Configuration (Set $SCRIPT_DIR ENV Variable in the cronjob command)
# * * * * * SCRIPT_DIR="/path/to/script" ./backup_database.sh
# Make sure to `chmod 0700 backup_database.sh`
# Then `git config core.fileMode false` to prevent git from complaining about file mode changes
DB_FILE="$SCRIPT_DIR/db.sqlite3"
BACKUP_DIR="$SCRIPT_DIR/database_backups"
MAX_BACKUPS=10

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

#####################################
########## BACKUP CREATION ##########
#####################################

LATEST_BACKUP=$(find "$BACKUP_DIR" -name "db_*.sqlite3" -type f -printf '%T@ %p\n' | sort -rn | head -n 1 | cut -d' ' -f2-)

# Backup only if database has a different size than the latest backup, or the latest backup is older than a day
if [ -z "$LATEST_BACKUP" ] || [ "$DB_FILE" -nt "$LATEST_BACKUP" ] || [ $(stat -c%s "$DB_FILE") -ne $(stat -c%s "$LATEST_BACKUP") ]; then
  # Generate timestamped filename
  TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
  BACKUP_FILE="$BACKUP_DIR/db_${TIMESTAMP}.sqlite3"

  # Perform the backup
  cp "$DB_FILE" "$BACKUP_FILE"

  if [[ $? -eq 0 ]]; then
    echo "Backup created: $BACKUP_FILE"
  else
    echo "Error creating backup. Exiting."
    exit 1
  fi
else
  echo "No backup needed. Database has not changed."
fi

##########################################
########## EXTRA BACKUP CLEANUP ##########
##########################################

# Remove old backups
find "$BACKUP_DIR" -name "db_*.sqlite3" -type f | sort -r | tail -n +51 | xargs rm

exit 0