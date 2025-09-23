# Verification script for Redis AOF persistence
# Usage: In PowerShell run: .\scripts\verify_redis_persistence.ps1
# This script assumes docker and docker compose are available and that docker-compose.yml exists in the repo root.

Write-Output "Starting Redis persistence verification..."

# Ensure container is running
docker compose up -d

# Set test key
Write-Output "Setting test key"
docker exec -it local-redis redis-cli SET verify_key "ok"

# Force AOF rewrite
Write-Output "Triggering BGREWRITEAOF"
docker exec -it local-redis redis-cli BGREWRITEAOF

# Wait a short moment for background rewrite to finish
Start-Sleep -Seconds 2

# Show persistence info
Write-Output "Persistence info:"
docker exec -it local-redis redis-cli INFO Persistence

# Show aof files
Write-Output "AOF dir listing:"
docker exec -it local-redis ls -la /data

docker exec -it local-redis ls -la /data/appendonlydir

# Restart container
Write-Output "Restarting container"
docker restart local-redis

# Check key after restart
Write-Output "Checking verify_key after restart:"
docker exec -it local-redis redis-cli GET verify_key

Write-Output "Done. If the key is present after restart, AOF persistence works."