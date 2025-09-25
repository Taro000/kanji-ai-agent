# Enhanced Slack Bot Event Organizer AI Agent - Deployment Guide

## 📋 Overview

This guide provides comprehensive instructions for deploying the Enhanced Slack Bot Event Organizer AI Agent to Google Cloud Platform (GCP) using Cloud Run. The system is built with a multi-agent architecture using the Agent Development Kit (ADK) framework.

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Slack App     │    │   Cloud Run      │    │   Firestore     │
│                 │────│   Container      │────│   Database      │
│ • Bot Events    │    │                  │    │                 │
│ • Direct Msgs   │    │ • ADK Framework  │    │ • Event Data    │
│ • Interactions  │    │ • Multi-Agents   │    │ • Participants  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                    ┌─────────┼─────────┐
               ┌────────┐ ┌─────────┐ ┌─────────────┐
               │Google  │ │ Google  │ │ ぐるなび    │
               │Calendar│ │ Places  │ │ API        │
               │API     │ │ API     │ │            │
               └────────┘ └─────────┘ └─────────────┘
```

## 🎯 Core Components

### Multi-Agent System
- **Coordination Agent**: Workflow orchestration and phase management
- **Participant Agent**: Direct message interactions and confirmations
- **Scheduling Agent**: Time slot optimization and availability analysis
- **Venue Agent**: Multi-API venue search with intelligent fallback
- **Calendar Agent**: Google Workspace integration and meeting room booking

### External Integrations
- **Slack Bolt SDK**: Event handling and natural language processing
- **Google Calendar API**: OAuth2.0 authentication and event management
- **Google Places API**: Venue search with rate limiting
- **ぐるなび API**: Japanese restaurant search with error handling
- **GCP Firestore**: NoSQL database with transaction support

## 🚀 Prerequisites

### GCP Setup
1. **Google Cloud Project**
   ```bash
   # Create new project
   gcloud projects create your-project-id
   gcloud config set project your-project-id

   # Enable required APIs
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable firestore.googleapis.com
   gcloud services enable secretmanager.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   ```

2. **Artifact Registry Repository**
   ```bash
   gcloud artifacts repositories create slack-bot-event-organizer \
     --repository-format=docker \
     --location=asia-northeast1
   ```

3. **Firestore Database**
   ```bash
   # Initialize Firestore in Native mode
   gcloud firestore databases create --location=asia-northeast1
   ```

### Slack App Setup
1. **Create Slack App**
   - Go to [Slack API](https://api.slack.com/apps)
   - Click "Create New App" → "From scratch"
   - Name: "Event Organizer AI"
   - Select your workspace

2. **Configure Bot Permissions**
   ```
   OAuth & Permissions → Bot Token Scopes:
   • chat:write
   • channels:read
   • im:write
   • im:read
   • users:read
   • users:read.email
   • app_mentions:read
   ```

3. **Enable Events**
   ```
   Event Subscriptions:
   • app_mention
   • message.im
   • message.channels

   Request URL: https://your-service-url/slack/events
   ```

4. **Install to Workspace**
   - Install App → Install to Workspace
   - Copy Bot User OAuth Token
   - Copy Signing Secret

### Google APIs Setup

#### Google Calendar API
1. **Enable API**
   ```bash
   gcloud services enable calendar-json.googleapis.com
   ```

2. **Create OAuth2.0 Credentials**
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - APIs & Services → Credentials
   - Create OAuth 2.0 Client ID
   - Application type: Web application
   - Authorized redirect URIs: `https://your-service-url/oauth/callback`

3. **Download JSON credentials**
   - Save client ID and client secret

#### Google Places API
1. **Enable API**
   ```bash
   gcloud services enable places-backend.googleapis.com
   ```

2. **Create API Key**
   ```bash
   gcloud alpha services api-keys create --display-name="Places API Key"
   ```

#### ぐるなび API
1. **Register at ぐるなび API**
   - Visit [ぐるなび API](https://api.gnavi.co.jp/)
   - Register for API access
   - Obtain API key

## 🔐 Secret Management

Store sensitive configuration in GCP Secret Manager:

```bash
# Slack credentials
echo -n "xoxb-your-slack-bot-token" | gcloud secrets create slack-bot-token --data-file=-
echo -n "your-slack-signing-secret" | gcloud secrets create slack-signing-secret --data-file=-

# Google Calendar OAuth2.0
echo -n "your-google-client-id" | gcloud secrets create google-calendar-client-id --data-file=-
echo -n "your-google-client-secret" | gcloud secrets create google-calendar-client-secret --data-file=-

# API keys
echo -n "your-google-places-api-key" | gcloud secrets create google-places-api-key --data-file=-
echo -n "your-gurume-navi-api-key" | gcloud secrets create gurume-navi-api-key --data-file=-

# Environment-specific secrets for staging
echo -n "xoxb-staging-slack-token" | gcloud secrets create slack-bot-token-staging --data-file=-
echo -n "staging-signing-secret" | gcloud secrets create slack-signing-secret-staging --data-file=-
```

## 🐳 Container Build & Deploy

### Local Development
```bash
# Install dependencies
poetry install

# Set up environment
cp .env.example .env
# Edit .env with your development configuration

# Run tests
poetry run pytest tests/ -v

# Run linting
poetry run ruff check src tests
poetry run mypy src

# Start development server
poetry run python -m src.main
```

### Docker Build
```bash
# Build container
docker build -t asia-northeast1-docker.pkg.dev/your-project-id/slack-bot-event-organizer/slack-bot-event-organizer:latest .

# Test container locally
docker run -p 8080:8080 \
  -e ENV=development \
  -e GCP_PROJECT_ID=your-project-id \
  asia-northeast1-docker.pkg.dev/your-project-id/slack-bot-event-organizer/slack-bot-event-organizer:latest

# Push to Artifact Registry
docker push asia-northeast1-docker.pkg.dev/your-project-id/slack-bot-event-organizer/slack-bot-event-organizer:latest
```

### Cloud Run Deployment

#### Production Deployment
```bash
gcloud run deploy slack-bot-event-organizer \
  --image=asia-northeast1-docker.pkg.dev/your-project-id/slack-bot-event-organizer/slack-bot-event-organizer:latest \
  --region=asia-northeast1 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --max-instances=20 \
  --min-instances=1 \
  --concurrency=80 \
  --port=8080 \
  --set-env-vars="ENV=production,GCP_PROJECT_ID=your-project-id,FIRESTORE_DATABASE=(default)" \
  --set-secrets="SLACK_BOT_TOKEN=slack-bot-token:latest" \
  --set-secrets="SLACK_SIGNING_SECRET=slack-signing-secret:latest" \
  --set-secrets="GOOGLE_CALENDAR_CLIENT_ID=google-calendar-client-id:latest" \
  --set-secrets="GOOGLE_CALENDAR_CLIENT_SECRET=google-calendar-client-secret:latest" \
  --set-secrets="GOOGLE_PLACES_API_KEY=google-places-api-key:latest" \
  --set-secrets="GURUME_NAVI_API_KEY=gurume-navi-api-key:latest" \
  --execution-environment=gen2
```

#### Staging Deployment
```bash
gcloud run deploy slack-bot-event-organizer-staging \
  --image=asia-northeast1-docker.pkg.dev/your-project-id/slack-bot-event-organizer/slack-bot-event-organizer:latest \
  --region=asia-northeast1 \
  --platform=managed \
  --allow-unauthenticated \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300 \
  --max-instances=5 \
  --min-instances=0 \
  --concurrency=80 \
  --port=8080 \
  --set-env-vars="ENV=staging,GCP_PROJECT_ID=your-project-id,FIRESTORE_DATABASE=(default)" \
  --set-secrets="SLACK_BOT_TOKEN=slack-bot-token-staging:latest" \
  --set-secrets="SLACK_SIGNING_SECRET=slack-signing-secret-staging:latest" \
  --set-secrets="GOOGLE_CALENDAR_CLIENT_ID=google-calendar-client-id-staging:latest" \
  --set-secrets="GOOGLE_CALENDAR_CLIENT_SECRET=google-calendar-client-secret-staging:latest" \
  --set-secrets="GOOGLE_PLACES_API_KEY=google-places-api-key-staging:latest" \
  --set-secrets="GURUME_NAVI_API_KEY=gurume-navi-api-key-staging:latest" \
  --execution-environment=gen2
```

## ⚙️ Environment Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ENV` | Environment (development/staging/production) | `production` |
| `GCP_PROJECT_ID` | Google Cloud Project ID | `my-slack-bot-project` |
| `FIRESTORE_DATABASE` | Firestore database ID | `(default)` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Required Secrets

| Secret Name | Description | Source |
|-------------|-------------|---------|
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token | Slack App Settings |
| `SLACK_SIGNING_SECRET` | Slack App Signing Secret | Slack App Settings |
| `GOOGLE_CALENDAR_CLIENT_ID` | Google Calendar OAuth2.0 Client ID | Google Cloud Console |
| `GOOGLE_CALENDAR_CLIENT_SECRET` | Google Calendar OAuth2.0 Client Secret | Google Cloud Console |
| `GOOGLE_PLACES_API_KEY` | Google Places API Key | Google Cloud Console |
| `GURUME_NAVI_API_KEY` | ぐるなび API Key | ぐるなび Developer Portal |

## 🤖 CI/CD Pipeline

The project includes comprehensive GitHub Actions workflows:

### Continuous Integration (.github/workflows/ci.yml)
- **Triggers**: Push to main/develop, Pull requests
- **Jobs**:
  - Lint and format checking (Ruff, mypy)
  - Multi-version testing (Python 3.11, 3.12)
  - Security scanning (Safety, Bandit)
  - Docker image building
  - Performance benchmarking

### Auto Deployment (.github/workflows/auto-deploy.yml)
- **Trigger**: Successful CI on main branch
- **Process**:
  1. Build and push Docker image
  2. Deploy to Cloud Run
  3. Health checks and smoke tests
  4. Automatic rollback on failure

### Manual Deployment (.github/workflows/manual-deploy.yml)
- **Trigger**: Manual workflow dispatch
- **Features**:
  - Environment selection (staging/production)
  - Custom image tag deployment
  - Pre-deployment validation
  - Optional test skipping
  - Force deployment option

### Release Management (.github/workflows/release-drafter.yml)
- **Trigger**: Pull request merge
- **Features**:
  - Automatic release notes generation
  - Semantic versioning
  - Change categorization
  - Release artifact creation

## 📊 Monitoring & Observability

### Health Check Endpoints
```
GET /health                    # Basic service health
GET /api/health/db            # Database connectivity
GET /api/health/agents        # Agent system status
GET /api/v1/version           # Service version info
```

### Logging
- **Structured logging** with Python `structlog`
- **Log levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **GCP Cloud Logging** integration
- **Request tracing** for debugging

### Metrics & Alerts
```bash
# Set up alerting policies
gcloud alpha monitoring policies create --policy-from-file=monitoring/alert-policies.yaml

# Create custom metrics
gcloud logging metrics create agent_response_time \
  --log-filter='resource.type="cloud_run_revision" AND jsonPayload.metric_name="agent_response_time"' \
  --description="Agent response time metric"
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Slack Events Not Received
**Symptoms**: Bot doesn't respond to mentions or DMs

**Solutions**:
```bash
# Check Cloud Run service logs
gcloud logs read --limit=50 --service=slack-bot-event-organizer

# Verify Slack webhook URL
curl -X POST https://your-service-url/slack/events \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test123"}'

# Check Slack App configuration
# Ensure Request URL is set correctly in Slack App settings
```

#### 2. Google Calendar Integration Issues
**Symptoms**: Calendar events not created

**Solutions**:
```bash
# Test OAuth2.0 flow
curl https://your-service-url/oauth/auth?user=test@example.com

# Check Google Calendar API quotas
gcloud logging read 'resource.type="cloud_run_revision" AND jsonPayload.error_type="quota_exceeded"'

# Verify OAuth2.0 credentials
gcloud secrets versions access latest --secret="google-calendar-client-id"
```

#### 3. Database Connection Issues
**Symptoms**: Firestore operations failing

**Solutions**:
```bash
# Test Firestore connectivity
curl https://your-service-url/api/health/db

# Check Firestore rules
gcloud firestore rules get

# Verify service account permissions
gcloud projects get-iam-policy your-project-id \
  --filter="bindings.members:*your-service-account*"
```

#### 4. Performance Issues
**Symptoms**: Slow response times, timeouts

**Solutions**:
```bash
# Run performance validation
python scripts/performance_validation.py

# Check Cloud Run metrics
gcloud run services describe slack-bot-event-organizer \
  --region=asia-northeast1 \
  --format="value(status.traffic)"

# Scale up resources if needed
gcloud run services update slack-bot-event-organizer \
  --region=asia-northeast1 \
  --memory=4Gi \
  --cpu=4
```

### Debug Commands

```bash
# View recent logs
gcloud logs read --limit=100 --service=slack-bot-event-organizer

# Check service status
gcloud run services describe slack-bot-event-organizer --region=asia-northeast1

# Test API endpoints
curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  https://your-service-url/api/v1/events

# Check secrets
gcloud secrets versions list slack-bot-token

# Monitor resource usage
gcloud monitoring metrics list --filter="resource.type=cloud_run_revision"
```

## 🔧 Maintenance

### Regular Tasks

#### 1. Secret Rotation (Monthly)
```bash
# Rotate Slack token
echo -n "new-slack-bot-token" | gcloud secrets create slack-bot-token-new --data-file=-
gcloud secrets versions list slack-bot-token

# Update Cloud Run service
gcloud run services update slack-bot-event-organizer \
  --region=asia-northeast1 \
  --set-secrets="SLACK_BOT_TOKEN=slack-bot-token-new:latest"
```

#### 2. Database Maintenance (Weekly)
```bash
# Check Firestore usage
gcloud firestore stats

# Cleanup old sessions (implement in application)
# Run database maintenance scripts
```

#### 3. Performance Monitoring (Daily)
```bash
# Run automated performance tests
python scripts/performance_validation.py

# Check error rates
gcloud logs read --filter='severity>=ERROR' --limit=20
```

### Backup & Recovery

#### 1. Firestore Backup
```bash
# Export Firestore data
gcloud firestore export gs://your-backup-bucket/firestore-backup-$(date +%Y%m%d)

# Set up automated backups
gcloud scheduler jobs create app-engine firestore-backup \
  --schedule="0 2 * * *" \
  --time-zone="Asia/Tokyo" \
  --uri="https://your-service-url/admin/backup"
```

#### 2. Configuration Backup
```bash
# Export secrets (metadata only)
gcloud secrets list --format="value(name)" > secrets-list.txt

# Export Cloud Run configuration
gcloud run services describe slack-bot-event-organizer \
  --region=asia-northeast1 \
  --format=export > cloud-run-config.yaml
```

## 📈 Scaling Considerations

### Horizontal Scaling
- **Cloud Run**: Auto-scales based on request load
- **Max instances**: Configure based on expected load
- **Concurrency**: Optimize based on agent coordination patterns

### Vertical Scaling
- **Memory**: Increase for large participant groups (>50 people)
- **CPU**: Increase for complex scheduling optimization
- **Timeout**: Adjust for venue search latency

### Database Scaling
- **Firestore**: Automatically scales, monitor read/write patterns
- **Indexes**: Create composite indexes for complex queries
- **Caching**: Implement Redis for frequent lookups

## 🛡️ Security Best Practices

### 1. Network Security
- Cloud Run with IAM authentication
- VPC integration for internal services
- HTTPS enforcement

### 2. Data Protection
- Encrypt sensitive data in Firestore
- Use GCP Secret Manager for credentials
- Implement audit logging

### 3. API Security
- Rate limiting for external APIs
- Input validation and sanitization
- OAuth2.0 token management

## 📞 Support & Resources

### Documentation
- [ADK Framework Docs](https://agent-development-kit.readthedocs.io/)
- [Slack Bolt SDK](https://slack.dev/bolt-python/tutorial/getting-started)
- [Google Cloud Run](https://cloud.google.com/run/docs)
- [Firestore Documentation](https://cloud.google.com/firestore/docs)

### Contact
- **Issues**: [GitHub Issues](https://github.com/your-username/slack-bot-event-organizer/issues)
- **Support**: Create support ticket in your organization's system
- **Emergency**: Follow your organization's incident response procedures

---

## ✅ Deployment Checklist

Before deploying to production, ensure:

- [ ] All secrets are properly configured in Secret Manager
- [ ] Slack App is installed and configured correctly
- [ ] Google APIs are enabled with appropriate quotas
- [ ] Firestore database is initialized
- [ ] CI/CD pipeline tests are passing
- [ ] Performance validation meets targets (<500ms)
- [ ] Security scanning shows no critical vulnerabilities
- [ ] Monitoring and alerting are configured
- [ ] Backup strategy is implemented
- [ ] Team has access to logs and metrics
- [ ] Emergency rollback procedure is documented

Happy deploying! 🚀