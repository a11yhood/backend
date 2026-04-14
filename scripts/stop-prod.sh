#!/bin/bash
# Stop backend production server for a11yhood
# Cleanly shuts down the backend server

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛑 Stopping a11yhood backend production server (Docker)...${NC}"
echo ""

# Stop production container
echo -e "${YELLOW}🔧 Stopping production container...${NC}"
if docker ps --filter "name=a11yhood-backend-prod" --format "{{.Names}}" | grep -q "a11yhood-backend-prod"; then
  docker stop a11yhood-backend-prod
  docker rm a11yhood-backend-prod
  echo -e "${GREEN}✓ Backend production container stopped${NC}"
else
  echo -e "${YELLOW}⚠️  No production container running${NC}"
fi

echo ""
echo -e "${GREEN}✅ Backend production server stopped${NC}"
echo ""
echo -e "${BLUE}💡 To restart production:${NC}"
echo "   ./start-prod.sh"
echo ""
echo -e "${BLUE}💡 To start development environment instead:${NC}"
echo "   ./start-dev.sh"
echo ""
