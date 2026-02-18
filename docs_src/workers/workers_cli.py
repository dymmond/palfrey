# Start four worker processes.
# palfrey myapp.main:app --workers 4 --host 0.0.0.0 --port 8080

# Worker mode and reload mode are mutually exclusive.
# palfrey myapp.main:app --reload --workers 2  # invalid
