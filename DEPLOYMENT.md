# Deployment Guide

This guide outlines the steps to deploy the Indonesia Supreme Court LLM Agent to production.

## Prerequisites

- Docker and Docker Compose installed on the production server
- Access to production environment variables
- GNU Make (for Makefile commands)
- HTTPS certificate for production deployment (recommended)

## Deployment Steps

1. Clone the repository on your production server:
   ```bash
   git clone <repository-url>
   cd indonesia-supreme-court-llm-agent
   ```

2. Configure production environment:
   Edit the `.env.production` file with your production credentials:
   ```
   OPENAI_API_KEY=your_production_api_key
   DB_ADDR=your_production_db_address
   DB_USER=your_production_db_user
   DB_PASS=your_production_db_password
   QDRANT_FILEPATH=/app/qdrant_storage
   PORT=8080
   LOG_LEVEL=INFO
   JSON_LOGS=true

   # Security Settings
   ENVIRONMENT=production
   API_KEY=generate_a_strong_random_api_key_here
   ALLOWED_HOSTS=your-domain.com,www.your-domain.com
   CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
   RATE_LIMIT=60
   ```

   **Security Note:** Generate a strong API key using a secure method, for example:
   ```bash
   openssl rand -hex 32
   ```

3. Build and start the application:
   ```bash
   make prod
   ```

   Or using docker-compose directly:
   ```bash
   docker-compose -f docker-compose.production.yml up -d
   ```

4. Verify the deployment:
   ```bash
   make health
   ```

   Or using curl directly:
   ```bash
   curl http://localhost:8080/health
   ```

## Security Configuration

The application includes several security features that should be configured for production:

### API Authentication

All API endpoints are protected with API key authentication. Clients must include the `X-API-Key` header with the API key specified in the environment variables.

Example API request:
```bash
curl -H "X-API-Key: your_api_key_here" -X POST "https://your-domain.com/chatbot/user_message?thread_id=123&user_message=Hello"
```

### CORS Protection

Cross-Origin Resource Sharing is configured to restrict which domains can access the API. Configure the `CORS_ORIGINS` variable with a comma-separated list of allowed domains.

### Rate Limiting

The API includes rate limiting to prevent abuse. The default is 60 requests per minute per IP address. Adjust this using the `RATE_LIMIT` environment variable.

### Trusted Hosts

Configure `ALLOWED_HOSTS` to specify which hostnames the application will accept requests from, preventing host header attacks.

### HTTPS Enforcement

In production mode, the application will force HTTPS connections. Ensure your reverse proxy (Nginx, etc.) is configured with a valid SSL certificate.

### Non-Root Container User

The Docker container runs as a non-root user for improved security.

## Using the Makefile

A Makefile is provided to simplify common operations. To see all available commands:

```bash
make help
```

### Common Make Commands

| Command | Description |
|---------|-------------|
| `make dev` | Run development server locally |
| `make prod` | Start production environment |
| `make logs` | View Docker logs |
| `make logs-tail` | Tail logs in real-time |
| `make logs-error` | View error logs |
| `make health` | Check application health |
| `make index` | Run the indexing process |
| `make backup` | Backup Qdrant data |
| `make backup-logs` | Backup log files |
| `make update` | Update and rebuild services |
| `make restart` | Restart services |
| `make clean` | Remove containers and volumes |

## Data Indexing

If you need to index court documents for the first time:

1. Run the indexing process:
   ```bash
   make index
   ```

   Or using docker-compose directly:
   ```bash
   docker-compose -f docker-compose.production.yml exec bo-chat python -m main.cli.index_court_docs_summary_content
   ```

## Updating the Deployment

To update the deployment:

1. Update the application:
   ```bash
   make update
   ```

   Or using git and docker-compose directly:
   ```bash
   git pull
   docker-compose -f docker-compose.production.yml down
   docker-compose -f docker-compose.production.yml up -d --build
   ```

## Production Security Recommendations

1. **Reverse Proxy:** Use Nginx or Apache as a reverse proxy in front of the application to handle SSL termination and additional security features.

2. **Firewall Configuration:** Configure a firewall to restrict access to only necessary ports (typically 80 and 443).

3. **Regular Updates:** Keep the host system, Docker, and application dependencies up to date with security patches.

4. **Intrusion Detection:** Consider deploying an intrusion detection system (IDS) to monitor for suspicious activities.

5. **Backups:** Regularly backup all data and ensure backups are stored securely.

6. **Secrets Management:** Consider using a secrets management solution like Docker secrets or HashiCorp Vault for sensitive credentials.

7. **Monitoring:** Implement comprehensive monitoring for both security and performance issues.

## Monitoring and Logging

### Log Configuration

The application uses structured JSON logging in production with the following features:
- Request ID tracking across all log messages
- Performance metrics for API requests
- Automatic log rotation
- Separate error logs
- Standard output (stdout/stderr) logging for Docker
- Security-related events logging

Logs are available through multiple channels:

1. **Docker Logs** - Standard output captured by Docker's logging system
2. **Container Volume Logs** - Persistent logs stored in Docker volumes:
   - Main logs: `/app/logs/app.log`
   - Error logs: `/app/logs/error.log`

### Accessing Logs

#### Using Make Commands

```bash
# View all logs
make logs

# Tail logs in real-time
make logs-tail

# View only error logs
make logs-error
```

#### Docker Logs (stdout/stderr)

- View real-time Docker logs:
  ```bash
  docker-compose -f docker-compose.production.yml logs -f bo-chat
  ```

- View recent Docker logs with timestamps:
  ```bash
  docker-compose -f docker-compose.production.yml logs --tail=100 --timestamps bo-chat
  ```

- Filter logs by error level (using grep):
  ```bash
  docker-compose -f docker-compose.production.yml logs bo-chat | grep '"level":"ERROR"'
  ```

#### Container Volume Logs

- Directly access file logs:
  ```bash
  docker-compose -f docker-compose.production.yml exec bo-chat cat /app/logs/app.log
  ```

- View only errors:
  ```bash
  docker-compose -f docker-compose.production.yml exec bo-chat cat /app/logs/error.log
  ```

- Tail logs in real-time:
  ```bash
  docker-compose -f docker-compose.production.yml exec bo-chat tail -f /app/logs/app.log
  ```

### Security Logging

Security-related events, such as unauthorized access attempts, rate limit violations, and invalid API keys, are logged with appropriate severity levels. Monitor these logs regularly for security issues.

To search for security-related events:
```bash
docker-compose -f docker-compose.production.yml logs bo-chat | grep -E 'rate limit|unauthorized|invalid|attempt'
```

### Health Checks

- Check application health:
  ```bash
  make health
  ```

- Container health check is configured to monitor the `/health` endpoint
- Check health status manually:
  ```bash
  docker ps  # Look for "healthy" status for the bo-chat container
  ```

## Backup

### Using Make Commands

```bash
# Backup Qdrant data
make backup

# Backup log files
make backup-logs
```

### Qdrant Data Backup

Qdrant data is stored in a Docker volume. To backup this data:

1. Create a backup of the Qdrant volume:
   ```bash
   docker run --rm -v indonesia-supreme-court-llm-agent_qdrant_data:/data -v $(pwd)/backups:/backups busybox tar -czf /backups/qdrant_backup_$(date +%Y%m%d).tar.gz /data
   ```

### Log Backup

To backup application logs:

1. Create a backup of the logs volume:
   ```bash
   docker run --rm -v indonesia-supreme-court-llm-agent_bo_chat_logs:/data -v $(pwd)/backups:/backups busybox tar -czf /backups/logs_backup_$(date +%Y%m%d).tar.gz /data
   ```

2. Store all backups in a secure location, preferably encrypted and off-site.