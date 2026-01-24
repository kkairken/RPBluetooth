#!/bin/bash
#
# RP3 Face Access Control - Management Script
# Usage: ./manage.sh [command]
#

SERVICE_NAME="face-access"
INSTALL_DIR="/home/hseadmin/RPBluetooth"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

case "$1" in
    start)
        echo -e "${GREEN}Starting $SERVICE_NAME...${NC}"
        sudo systemctl start "$SERVICE_NAME"
        sleep 2
        sudo systemctl status "$SERVICE_NAME" --no-pager
        ;;

    stop)
        echo -e "${YELLOW}Stopping $SERVICE_NAME...${NC}"
        sudo systemctl stop "$SERVICE_NAME"
        ;;

    restart)
        echo -e "${YELLOW}Restarting $SERVICE_NAME...${NC}"
        sudo systemctl restart "$SERVICE_NAME"
        sleep 2
        sudo systemctl status "$SERVICE_NAME" --no-pager
        ;;

    status)
        sudo systemctl status "$SERVICE_NAME" --no-pager
        ;;

    logs)
        echo -e "${BLUE}Showing live logs (Ctrl+C to exit)...${NC}"
        sudo journalctl -u "$SERVICE_NAME" -f
        ;;

    logs-today)
        sudo journalctl -u "$SERVICE_NAME" --since today
        ;;

    logs-errors)
        echo -e "${RED}Showing error logs...${NC}"
        sudo journalctl -u "$SERVICE_NAME" -p err --since "24 hours ago"
        ;;

    enable)
        echo -e "${GREEN}Enabling $SERVICE_NAME to start on boot...${NC}"
        sudo systemctl enable "$SERVICE_NAME"
        ;;

    disable)
        echo -e "${YELLOW}Disabling $SERVICE_NAME from starting on boot...${NC}"
        sudo systemctl disable "$SERVICE_NAME"
        ;;

    test)
        echo -e "${BLUE}Running in test mode (foreground)...${NC}"
        cd "$INSTALL_DIR"
        sudo "$INSTALL_DIR/venv/bin/python" -u src/main.py \
            --config config/production.yaml \
            --log-level DEBUG
        ;;

    test-mock)
        echo -e "${BLUE}Running in mock mode (no GPIO/BLE)...${NC}"
        cd "$INSTALL_DIR"
        sudo "$INSTALL_DIR/venv/bin/python" -u src/main.py \
            --config config/usb_config.yaml \
            --log-level DEBUG
        ;;

    backup)
        BACKUP_DIR="/home/hseadmin/backups"
        BACKUP_FILE="$BACKUP_DIR/face_access_$(date +%Y%m%d_%H%M%S).tar.gz"
        mkdir -p "$BACKUP_DIR"
        echo -e "${BLUE}Creating backup...${NC}"
        tar -czf "$BACKUP_FILE" \
            -C "$INSTALL_DIR" \
            data/ \
            config/production.yaml \
            logs/
        echo -e "${GREEN}Backup created: $BACKUP_FILE${NC}"
        ;;

    db-export)
        OUTPUT_FILE="${2:-/home/hseadmin/audit_logs_$(date +%Y%m%d).json}"
        echo -e "${BLUE}Exporting audit logs to $OUTPUT_FILE...${NC}"
        cd "$INSTALL_DIR"
        "$INSTALL_DIR/venv/bin/python" src/main.py \
            --config config/production.yaml \
            --export-logs "$OUTPUT_FILE"
        echo -e "${GREEN}Export complete: $OUTPUT_FILE${NC}"
        ;;

    health)
        echo -e "${BLUE}System Health Check${NC}"
        echo "================================"

        # Service status
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            echo -e "Service:    ${GREEN}Running${NC}"
        else
            echo -e "Service:    ${RED}Stopped${NC}"
        fi

        # Memory usage
        MEM=$(free -m | awk 'NR==2{printf "%.1f%%", $3*100/$2}')
        echo "Memory:     $MEM used"

        # Disk usage
        DISK=$(df -h "$INSTALL_DIR" | awk 'NR==2{print $5}')
        echo "Disk:       $DISK used"

        # Database size
        if [ -f "$INSTALL_DIR/data/access_control.db" ]; then
            DB_SIZE=$(du -h "$INSTALL_DIR/data/access_control.db" | cut -f1)
            echo "Database:   $DB_SIZE"
        fi

        # Log size
        LOG_SIZE=$(du -sh "$INSTALL_DIR/logs" 2>/dev/null | cut -f1)
        echo "Logs:       $LOG_SIZE"

        # Uptime
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            UPTIME=$(systemctl show "$SERVICE_NAME" --property=ActiveEnterTimestamp | cut -d= -f2)
            echo "Started:    $UPTIME"
        fi

        # Error count (last 24h)
        ERROR_COUNT=$(sudo journalctl -u "$SERVICE_NAME" -p err --since "24 hours ago" --no-pager 2>/dev/null | wc -l)
        if [ "$ERROR_COUNT" -gt 0 ]; then
            echo -e "Errors(24h): ${YELLOW}$ERROR_COUNT${NC}"
        else
            echo -e "Errors(24h): ${GREEN}0${NC}"
        fi
        ;;

    clean-logs)
        echo -e "${YELLOW}Cleaning old logs...${NC}"
        # Keep last 7 days of logs
        find "$INSTALL_DIR/logs" -name "*.log.*" -mtime +7 -delete
        sudo journalctl --vacuum-time=7d
        echo -e "${GREEN}Done${NC}"
        ;;

    *)
        echo "RP3 Face Access Control - Management"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  start       - Start the service"
        echo "  stop        - Stop the service"
        echo "  restart     - Restart the service"
        echo "  status      - Show service status"
        echo "  logs        - Show live logs"
        echo "  logs-today  - Show today's logs"
        echo "  logs-errors - Show error logs (24h)"
        echo "  enable      - Enable autostart on boot"
        echo "  disable     - Disable autostart"
        echo "  test        - Run in foreground (debug)"
        echo "  test-mock   - Run in mock mode (no GPIO)"
        echo "  backup      - Backup data and config"
        echo "  db-export   - Export audit logs to JSON"
        echo "  health      - Show system health"
        echo "  clean-logs  - Clean old log files"
        exit 1
        ;;
esac
