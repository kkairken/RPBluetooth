#!/bin/bash
#
# RP3 Face Access - Health Check Script
# For use with monitoring systems (cron, nagios, etc.)
# Exit codes: 0=OK, 1=Warning, 2=Critical
#

SERVICE_NAME="face-access"
INSTALL_DIR="/home/hseadmin/RPBluetooth"
MAX_ERROR_COUNT=10
MAX_MEMORY_PERCENT=80
MAX_DISK_PERCENT=90

# Check if service is running
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "CRITICAL: Service $SERVICE_NAME is not running"
    exit 2
fi

# Check for too many errors in last hour
ERROR_COUNT=$(journalctl -u "$SERVICE_NAME" -p err --since "1 hour ago" --no-pager 2>/dev/null | wc -l)
if [ "$ERROR_COUNT" -gt "$MAX_ERROR_COUNT" ]; then
    echo "WARNING: $ERROR_COUNT errors in last hour"
    exit 1
fi

# Check memory usage
MEM_PERCENT=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
if [ "$MEM_PERCENT" -gt "$MAX_MEMORY_PERCENT" ]; then
    echo "WARNING: Memory usage is ${MEM_PERCENT}%"
    exit 1
fi

# Check disk usage
DISK_PERCENT=$(df "$INSTALL_DIR" | awk 'NR==2{gsub(/%/,""); print $5}')
if [ "$DISK_PERCENT" -gt "$MAX_DISK_PERCENT" ]; then
    echo "WARNING: Disk usage is ${DISK_PERCENT}%"
    exit 1
fi

# Check database file exists and is not corrupted
DB_FILE="$INSTALL_DIR/data/access_control.db"
if [ ! -f "$DB_FILE" ]; then
    echo "CRITICAL: Database file not found"
    exit 2
fi

# Quick SQLite integrity check
if command -v sqlite3 &> /dev/null; then
    INTEGRITY=$(sqlite3 "$DB_FILE" "PRAGMA quick_check;" 2>&1)
    if [ "$INTEGRITY" != "ok" ]; then
        echo "CRITICAL: Database integrity check failed"
        exit 2
    fi
fi

# All OK
UPTIME=$(systemctl show "$SERVICE_NAME" --property=ActiveEnterTimestamp | cut -d= -f2)
echo "OK: Service running since $UPTIME, $ERROR_COUNT errors/hour, ${MEM_PERCENT}% mem, ${DISK_PERCENT}% disk"
exit 0
