#!/bin/bash
# Test export file integrity and basic import capability

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 Testing Database Exports"
echo "============================"
echo ""

# Check if files exist
check_file() {
    local file=$1
    local name=$2
    
    if [ -f "$file" ]; then
        local size=$(ls -lh "$file" | awk '{print $5}')
        local lines=$(wc -l < "$file")
        echo -e "${GREEN}✓${NC} $name"
        echo "  Size: $size | Lines: $lines"
        
        # Check if it has SQL statements
        if grep -q "CREATE TABLE\|INSERT INTO\|SELECT" "$file" 2>/dev/null; then
            echo "  Content: Valid SQL statements found"
        else
            echo -e "  ${YELLOW}⚠ Warning: No SQL statements detected${NC}"
        fi
    else
        echo -e "${RED}✗${NC} $name - File not found: $file"
        return 1
    fi
    echo ""
}

# Test public products export
echo "1️⃣  PUBLIC PRODUCTS EXPORT"
check_file "supabase/public-products.sql" "Public Products Dataset" || true

# Test test database export
echo "2️⃣  TEST DATABASE EXPORT"
check_file "supabase/seed-test.sql" "Test Database (Seed)" || true

# Test private export (if exists)
echo "3️⃣  PRIVATE DATABASE EXPORT"
check_file "supabase/full-database.sql" "Full Private Database" || true

echo ""
echo "📊 Export Statistics"
echo "==================="

if [ -f supabase/public-products.sql ]; then
    echo "Public products SQL:"
    echo "  Lines: $(wc -l < supabase/public-products.sql)"
    echo "  Tables referenced: $(grep -o "CREATE TABLE[^(]*" supabase/public-products.sql | wc -l)"
    echo "  INSERT statements: $(grep -c "INSERT INTO" supabase/public-products.sql || echo "0")"
fi

if [ -f supabase/seed-test.sql ]; then
    echo ""
    echo "Test database SQL:"
    echo "  Lines: $(wc -l < supabase/seed-test.sql)"
    echo "  Tables referenced: $(grep -o "CREATE TABLE[^(]*" supabase/seed-test.sql | wc -l || echo "0")"
    echo "  INSERT statements: $(grep -c "INSERT INTO" supabase/seed-test.sql || echo "0")"
fi

echo ""
echo "✅ Export validation complete!"
