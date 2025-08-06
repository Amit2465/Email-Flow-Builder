# EmailBuilder - Advanced Email Marketing Automation System

A sophisticated email marketing automation system with complex conditional branching logic, parallel execution paths, event-based triggering, and timeout mechanisms.

## 🏗️ Architecture Overview

### Core Components

- **Frontend**: React/Next.js with React Flow for visual campaign builder
- **Backend**: FastAPI with Celery for background task processing
- **Database**: MongoDB for data persistence
- **Message Queue**: RabbitMQ for Celery task coordination
- **Email Service**: SMTP integration with tracking capabilities

### Key Features

- **Conditional Logic**: Email open and link click tracking with YES/NO branching
- **Parallel Execution**: Simultaneous execution of multiple paths
- **Event-Driven**: Real-time event processing and flow interruption
- **Timeout Mechanisms**: Automatic NO branch execution as fallback
- **Campaign Management**: Complete lifecycle from creation to completion

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Node.js 16+
- MongoDB
- RabbitMQ
- Docker (optional)

### Backend Setup

1. **Install Dependencies**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Environment Configuration**
   ```bash
   # Create .env file
   cp .env.example .env
   
   # Configure your environment variables
   MONGODB_URL=mongodb://localhost:27017/emailbuilder
   RABBITMQ_URL=amqp://guest:guest@localhost:5672/
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

3. **Database Setup**
   ```bash
   # Start MongoDB
   mongod --dbpath /path/to/data/db
   
   # The application will automatically create collections on first run
   ```

4. **Start Services**
   ```bash
   # Terminal 1: Start FastAPI server
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   
   # Terminal 2: Start Celery worker
   cd backend
   celery -A app.celery_worker worker --loglevel=info
   
   # Terminal 3: Start Celery beat (for scheduled tasks)
   cd backend
   celery -A app.celery_worker beat --loglevel=info
   ```

### Frontend Setup

1. **Install Dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Start Development Server**
   ```bash
   npm run dev
   ```

3. **Access the Application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## 🔧 API Endpoints

### Campaign Management
- `POST /api/campaigns` - Create and start a new campaign
- `DELETE /api/campaigns/{campaign_id}/cleanup` - Clean up completed campaign data

### Tracking Endpoints
- `GET /api/track/open?token={token}` - Track email opens
- `GET /api/track/click?token={token}&url={url}` - Track link clicks

### Health & Monitoring
- `GET /health` - System health check with statistics
- `GET /` - API root endpoint

## 🏃‍♂️ Running with Docker

### Using Docker Compose

1. **Start all services**
   ```bash
   docker-compose up -d
   ```

2. **View logs**
   ```bash
   docker-compose logs -f
   ```

3. **Stop services**
   ```bash
   docker-compose down
   ```

### Manual Docker Setup

```bash
# Build images
docker build -t emailbuilder-backend ./backend
docker build -t emailbuilder-frontend ./frontend

# Run containers
docker run -d --name mongodb mongo:latest
docker run -d --name rabbitmq rabbitmq:3-management
docker run -d --name backend emailbuilder-backend
docker run -d --name frontend emailbuilder-frontend
```

## 📊 System Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

Response includes:
- Database connection status
- Celery worker status
- System statistics (leads, events, campaigns)

### Log Monitoring
```bash
# Backend logs
tail -f backend/logs/app.log

# Celery worker logs
tail -f backend/logs/celery.log
```

## 🔍 Troubleshooting

### Common Issues

1. **Celery Worker Not Starting**
   ```bash
   # Check RabbitMQ connection
   rabbitmq-diagnostics ping
   
   # Restart Celery with debug
   celery -A app.celery_worker worker --loglevel=debug
   ```

2. **Database Connection Issues**
   ```bash
   # Check MongoDB status
   mongo --eval "db.adminCommand('ping')"
   
   # Verify connection string
   echo $MONGODB_URL
   ```

3. **Email Tracking Not Working**
   ```bash
   # Check ngrok tunnel
   curl http://localhost:4040/api/tunnels
   
   # Verify tracking URLs in emails
   curl "http://localhost:8000/api/track/open?token=test"
   ```

4. **Campaign Stuck in Running State**
   ```bash
   # Check for stuck leads
   curl -X POST http://localhost:8000/api/debug/recover-stuck-leads
   
   # View campaign status
   curl http://localhost:8000/api/campaigns/{campaign_id}
   ```

### Performance Optimization

1. **Database Indexes**
   ```javascript
   // Create indexes for better performance
   db.leads.createIndex({"campaign_id": 1, "status": 1})
   db.leads.createIndex({"lead_id": 1, "campaign_id": 1})
   db.events.createIndex({"lead_id": 1, "processed": 1})
   ```

2. **Celery Configuration**
   ```python
   # Increase worker concurrency
   celery -A app.celery_worker worker --concurrency=4 --loglevel=info
   ```

3. **Memory Management**
   ```python
   # Enable result backend cleanup
   CELERY_RESULT_EXPIRES = 3600  # 1 hour
   CELERY_TASK_RESULT_EXPIRES = 3600
   ```

## 🧪 Testing

### Manual Testing

1. **Create Test Campaign**
   ```bash
   curl -X POST http://localhost:8000/api/campaigns \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Test Campaign",
       "contact_file": {
         "emails": ["test@example.com"]
       },
       "flow": {...}
     }'
   ```

2. **Test Email Tracking**
   ```bash
   # Simulate email open
   curl "http://localhost:8000/api/track/open?token=YOUR_TOKEN"
   
   # Simulate link click
   curl "http://localhost:8000/api/track/click?token=YOUR_TOKEN&url=https://example.com"
   ```

### Automated Testing

```bash
# Run backend tests
cd backend
pytest tests/

# Run frontend tests
cd frontend
npm test
```

## 📈 Production Deployment

### Environment Variables
```bash
# Production settings
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info
CORS_ORIGINS=https://yourdomain.com
SECRET_KEY=your-production-secret-key
```

### Security Considerations
- Use HTTPS in production
- Implement proper authentication
- Set up rate limiting
- Configure firewall rules
- Use environment-specific secrets

### Scaling
- Horizontal scaling with multiple Celery workers
- Database read replicas
- Load balancer for API endpoints
- CDN for static assets

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
- Check the troubleshooting section
- Review the logs for error messages
- Create an issue with detailed information
- Include system configuration and error logs 