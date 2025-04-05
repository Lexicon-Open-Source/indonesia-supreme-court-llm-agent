.PHONY: help dev build prod logs logs-error logs-tail backup backup-logs index clean health restart update

# Default goal
.DEFAULT_GOAL := help

# Color definitions
YELLOW=\033[0;33m
GREEN=\033[0;32m
NC=\033[0m # No Color

# Help command
help:
	@echo "$(GREEN)Indonesia Supreme Court LLM Agent Makefile$(NC)"
	@echo "$(YELLOW)Available commands:$(NC)"
	@echo "  $(YELLOW)help$(NC)         - Show this help message"
	@echo "  $(YELLOW)dev$(NC)          - Run development server locally"
	@echo "  $(YELLOW)build$(NC)        - Build Docker image"
	@echo "  $(YELLOW)prod$(NC)         - Run in production mode with Docker Compose"
	@echo "  $(YELLOW)logs$(NC)         - View Docker logs"
	@echo "  $(YELLOW)logs-error$(NC)   - View only error logs"
	@echo "  $(YELLOW)logs-tail$(NC)    - Tail logs in real-time"
	@echo "  $(YELLOW)health$(NC)       - Check application health"
	@echo "  $(YELLOW)index$(NC)        - Run indexing process"
	@echo "  $(YELLOW)backup$(NC)       - Backup Qdrant data"
	@echo "  $(YELLOW)backup-logs$(NC)  - Backup log files"
	@echo "  $(YELLOW)clean$(NC)        - Remove containers and volumes"
	@echo "  $(YELLOW)restart$(NC)      - Restart production services"
	@echo "  $(YELLOW)update$(NC)       - Update and rebuild production services"

# Development environment
dev:
	@echo "$(GREEN)Starting development server...$(NC)"
	@mkdir -p logs
	@uv run uvicorn main.http_server.app:app --port 8080 --host 0.0.0.0 --reload

# Build Docker image
build:
	@echo "$(GREEN)Building Docker image...$(NC)"
	@docker-compose build

# Production environment
prod:
	@echo "$(GREEN)Starting production environment...$(NC)"
	@docker-compose -f docker-compose.production.yml up -d
	@echo "$(GREEN)Application running in production mode$(NC)"

# View logs
logs:
	@echo "$(GREEN)Viewing logs...$(NC)"
	@docker-compose -f docker-compose.production.yml logs bo-chat

# View error logs only
logs-error:
	@echo "$(GREEN)Viewing error logs...$(NC)"
	@docker-compose -f docker-compose.production.yml exec bo-chat cat /app/logs/error.log

# Tail logs in real-time
logs-tail:
	@echo "$(GREEN)Tailing logs in real-time...$(NC)"
	@docker-compose -f docker-compose.production.yml logs -f bo-chat

# Health check
health:
	@echo "$(GREEN)Checking application health...$(NC)"
	@curl -s http://localhost:8080/health || echo "$(YELLOW)Application is not running or health check failed$(NC)"
	@echo "\n$(GREEN)Container status:$(NC)"
	@docker ps | grep bo-chat

# Run indexing process
index:
	@echo "$(GREEN)Running indexing process...$(NC)"
	@docker-compose -f docker-compose.production.yml exec bo-chat python -m main.cli.index_court_docs_summary_content

# Backup Qdrant data
backup:
	@echo "$(GREEN)Backing up Qdrant data...$(NC)"
	@mkdir -p backups
	@docker run --rm -v indonesia-supreme-court-llm-agent_qdrant_data:/data -v $(PWD)/backups:/backups busybox tar -czf /backups/qdrant_backup_$(shell date +%Y%m%d).tar.gz /data
	@echo "$(GREEN)Backup completed: backups/qdrant_backup_$(shell date +%Y%m%d).tar.gz$(NC)"

# Backup log files
backup-logs:
	@echo "$(GREEN)Backing up log files...$(NC)"
	@mkdir -p backups
	@docker run --rm -v indonesia-supreme-court-llm-agent_bo_chat_logs:/data -v $(PWD)/backups:/backups busybox tar -czf /backups/logs_backup_$(shell date +%Y%m%d).tar.gz /data
	@echo "$(GREEN)Backup completed: backups/logs_backup_$(shell date +%Y%m%d).tar.gz$(NC)"

# Clean up
clean:
	@echo "$(GREEN)Cleaning up containers and volumes...$(NC)"
	@docker-compose -f docker-compose.production.yml down -v
	@echo "$(GREEN)Cleanup completed$(NC)"

# Restart services
restart:
	@echo "$(GREEN)Restarting services...$(NC)"
	@docker-compose -f docker-compose.production.yml restart
	@echo "$(GREEN)Services restarted$(NC)"

# Update and rebuild
update:
	@echo "$(GREEN)Updating services...$(NC)"
	@git pull
	@docker-compose -f docker-compose.production.yml down
	@docker-compose -f docker-compose.production.yml up -d --build
	@echo "$(GREEN)Services updated and rebuilt$(NC)"