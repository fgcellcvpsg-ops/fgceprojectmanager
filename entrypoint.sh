#!/usr/bin/env bash
# exit on error
set -o errexit

# Run migrations
echo "Running migrations..."
# Check if migration directory exists and database is not empty
# If needed, we can use 'flask db stamp head' to mark current state as latest if tables exist but migration history is missing
flask db upgrade || {
    echo "Migration failed! Attempting to stamp head and retry..."
    flask db stamp head
    flask db upgrade
}

# Seed admin
echo "Seeding admin..."
python seed_admin.py

# Start app
echo "Starting Gunicorn..."
exec gunicorn run:app