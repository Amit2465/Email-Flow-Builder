#!/bin/bash

# EmailBuilder Storage Setup Script for 20GB EC2 t2.micro
# This script sets up storage directories and cleanup policies for optimal resource management

# Exit on any error
set -e

echo "Setting up storage for EmailBuilder on 20GB EC2..."

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run with sudo"
    echo "Usage: sudo ./setup-storage.sh"
    exit 1
fi

# Create storage directories
echo "Creating storage directories..."
mkdir -p /opt/mongodb_data
mkdir -p /opt/rabbitmq_data
mkdir -p /opt/docker_logs

# Set permissions (999 is the default user for MongoDB and RabbitMQ containers)
echo "Setting permissions..."
chown -R 999:999 /opt/mongodb_data
chown -R 999:999 /opt/rabbitmq_data
chmod 755 /opt/docker_logs

# Create logrotate configuration for Docker
echo "Setting up log rotation..."
cat > /etc/logrotate.d/docker-containers << 'EOF'
/var/lib/docker/containers/*/*.log {
    rotate 3
    daily
    compress
    size=2M
    missingok
    delaycompress
    copytruncate
    notifempty
}
EOF

# Create cleanup script
echo "Creating cleanup script..."
cat > /usr/local/bin/docker-cleanup << 'EOF'
#!/bin/bash

echo "Cleaning up Docker resources..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running"
    exit 1
fi

# Remove unused containers
echo "Removing unused containers..."
docker container prune -f

# Remove unused images
echo "Removing unused images..."
docker image prune -f

# Remove unused volumes
echo "Removing unused volumes..."
docker volume prune -f

# Remove unused networks
echo "Removing unused networks..."
docker network prune -f

# Clean up system
echo "Cleaning up system..."
docker system prune -f

echo "Cleanup completed!"
EOF

chmod +x /usr/local/bin/docker-cleanup

# Create storage monitoring script
echo "Creating storage monitoring script..."
cat > /usr/local/bin/check-storage << 'EOF'
#!/bin/bash

echo "Storage Usage Report:"
echo "===================="

# Check disk usage
echo "Disk Usage:"
df -h

echo ""
echo "Docker Storage:"
if docker info > /dev/null 2>&1; then
    docker system df
else
    echo "Docker is not running"
fi

echo ""
echo "Directory Sizes:"
if [ -d "/opt/mongodb_data" ]; then
    du -sh /opt/mongodb_data 2>/dev/null || echo "MongoDB data directory not accessible"
fi
if [ -d "/opt/rabbitmq_data" ]; then
    du -sh /opt/rabbitmq_data 2>/dev/null || echo "RabbitMQ data directory not accessible"
fi
if [ -d "/var/lib/docker/containers" ]; then
    du -sh /var/lib/docker/containers 2>/dev/null || echo "Docker containers directory not accessible"
fi

echo ""
echo "Container Log Sizes:"
if [ -d "/var/lib/docker/containers" ]; then
    find /var/lib/docker/containers -name "*.log" -exec ls -lh {} \; 2>/dev/null | head -10
else
    echo "Docker containers directory not found"
fi

echo ""
echo "To clean up: sudo /usr/local/bin/docker-cleanup"
EOF

chmod +x /usr/local/bin/check-storage

# Set up cron job for daily cleanup
echo "Setting up daily cleanup cron job..."
# Remove existing cron job if it exists
crontab -l 2>/dev/null | grep -v "docker-cleanup" | crontab -
# Add new cron job
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/docker-cleanup") | crontab -

echo ""
echo "Storage setup completed!"
echo ""
echo "Available commands:"
echo "  check-storage    - Check storage usage"
echo "  docker-cleanup   - Clean up Docker resources"
echo ""
echo "Current storage usage:"
/usr/local/bin/check-storage
