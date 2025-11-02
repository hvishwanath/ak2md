#!/bin/bash
# build_and_sync.sh - Complete build and sync pipeline for Kafka documentation

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEST="${1:-/Users/hvishwanath/projects/kafka-site}"
DRY_RUN="${2:-false}"

# Function to print colored messages
print_step() {
    echo -e "${BLUE}==>${NC} ${GREEN}$1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_error() {
    echo -e "${RED}✗${NC}  $1"
}

print_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

# Print banner
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Kafka Documentation Build & Sync Pipeline                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if destination directory exists
if [ ! -d "$DEST" ]; then
    print_error "Destination directory does not exist: $DEST"
    print_info "Please specify a valid destination directory"
    print_info "Usage: $0 [destination] [dry-run]"
    print_info "Example: $0 /path/to/hugo/site"
    exit 1
fi

print_info "Destination: $DEST"
if [ "$DRY_RUN" = "true" ]; then
    print_warning "DRY RUN MODE - No changes will be made"
fi
echo ""

# Step 1: Process HTML to Markdown
print_step "Step 1: Processing HTML to Markdown"
print_info "Running main.py to convert HTML source to markdown..."
echo ""
if python main.py; then
    print_success "HTML to Markdown conversion completed successfully"
else
    print_error "HTML to Markdown conversion failed"
    exit 1
fi
echo ""

# Step 2: Sync to Hugo site
print_step "Step 2: Syncing to Hugo site"
print_info "Syncing workspace/output to $DEST..."
echo ""
if [ "$DRY_RUN" = "true" ]; then
    if python sync_to_hugo.py --dest "$DEST" --dry-run; then
        print_success "Dry run completed successfully"
        print_warning "No files were actually synced (dry run mode)"
    else
        print_error "Sync dry run failed"
        exit 1
    fi
else
    if python sync_to_hugo.py --dest "$DEST"; then
        print_success "Sync completed successfully"
    else
        print_error "Sync failed"
        exit 1
    fi
fi
echo ""

# Step 3: Optional - Build Hugo site
if [ "$DRY_RUN" != "true" ]; then
    print_step "Step 3: Build Hugo site (optional)"
    print_info "You can now build the Hugo site:"
    echo -e "  ${BLUE}cd $DEST${NC}"
    echo -e "  ${BLUE}hugo${NC}"
    echo ""
    
    # Ask if user wants to build now
    read -p "Do you want to build the Hugo site now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Building Hugo site..."
        cd "$DEST"
        if hugo; then
            print_success "Hugo site built successfully"
            print_info "Output location: $DEST/public"
        else
            print_error "Hugo build failed"
            exit 1
        fi
    else
        print_info "Skipping Hugo build"
    fi
fi

# Done
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Pipeline completed successfully!                         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Summary
print_info "Next steps:"
if [ "$DRY_RUN" = "true" ]; then
    echo "  1. Run without dry-run to actually sync files:"
    echo -e "     ${BLUE}$0 $DEST${NC}"
else
    echo "  1. Review the changes in: $DEST"
    echo "  2. Build the Hugo site:"
    echo -e "     ${BLUE}cd $DEST && hugo${NC}"
    echo "  3. Preview the site:"
    echo -e "     ${BLUE}cd $DEST && hugo server${NC}"
fi
echo ""

