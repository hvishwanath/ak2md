#!/bin/bash
# build_and_sync.sh - Complete build and sync pipeline for Kafka documentation

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default Configuration
DEST="/Users/hvishwanath/projects/kafka-site"
DRY_RUN="false"
DO_BUILD="true"
DO_SYNC="true"
DO_HUGO="false"

# Determine Python command
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif [ -f ".venv/bin/python3" ]; then
    PYTHON_CMD=".venv/bin/python3"
else
    PYTHON_CMD="python3"
fi


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

# Help function
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dest <path>    Destination directory (default: $DEST)"
    echo "  --dry-run        Enable dry run mode (no changes will be made)"
    echo "  --build-only     Run only the HTML to Markdown conversion"
    echo "  --sync-only      Run only the sync to Hugo site"
    echo "  --hugo           Build the Hugo site after syncing"
    echo "  --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --dest /path/to/site"
    echo "  $0 --build-only"
    echo "  $0 --sync-only --dry-run"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dest)
            DEST="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --build-only)
            DO_BUILD="true"
            DO_SYNC="false"
            shift
            ;;
        --sync-only)
            DO_BUILD="false"
            DO_SYNC="true"
            shift
            ;;
        --hugo)
            DO_HUGO="true"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            # Check if it's a positional argument for backward compatibility
            if [ -z "$DEST_SET" ] && [[ "$1" != -* ]]; then
                DEST="$1"
                DEST_SET="true"
                shift
            elif [ -z "$DRY_RUN_SET" ] && [[ "$1" == "true" || "$1" == "false" ]]; then
                DRY_RUN="$1"
                DRY_RUN_SET="true"
                shift
            else
                print_error "Unknown option: $1"
                show_help
                exit 1
            fi
            ;;
    esac
done

# Print banner
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Kafka Documentation Build & Sync Pipeline                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if destination directory exists if we are syncing
if [ "$DO_SYNC" = "true" ]; then
    if [ ! -d "$DEST" ]; then
        print_error "Destination directory does not exist: $DEST"
        print_info "Please specify a valid destination directory"
        print_info "Usage: $0 --dest <path>"
        exit 1
    fi
    print_info "Destination: $DEST"
fi

if [ "$DRY_RUN" = "true" ]; then
    print_warning "DRY RUN MODE - No changes will be made"
fi
echo ""

# Step 1: Process HTML to Markdown
if [ "$DO_BUILD" = "true" ]; then
    print_step "Step 1: Processing HTML to Markdown"
    print_info "Running main.py to convert HTML source to markdown..."
    echo ""
    if $PYTHON_CMD main.py; then
        print_success "HTML to Markdown conversion completed successfully"
    else
        print_error "HTML to Markdown conversion failed"
        exit 1
    fi
    echo ""
else
    print_info "Skipping Step 1: HTML to Markdown conversion"
fi

# Step 2: Sync to Hugo site
if [ "$DO_SYNC" = "true" ]; then
    print_step "Step 2: Syncing to Hugo site"
    print_info "Syncing workspace/output to $DEST..."
    echo ""
    if [ "$DRY_RUN" = "true" ]; then
        if $PYTHON_CMD sync_to_hugo.py --dest "$DEST" --dry-run; then
            print_success "Dry run completed successfully"
            print_warning "No files were actually synced (dry run mode)"
        else
            print_error "Sync dry run failed"
            exit 1
        fi
    else
        if $PYTHON_CMD sync_to_hugo.py --dest "$DEST"; then
            print_success "Sync completed successfully"
        else
            print_error "Sync failed"
            exit 1
        fi
    fi
    echo ""
else
    print_info "Skipping Step 2: Syncing to Hugo site"
fi

# Step 3: Optional - Build Hugo site
if [ "$DO_HUGO" = "true" ] && [ "$DRY_RUN" != "true" ]; then
    print_step "Step 3: Build Hugo site"
    print_info "Building Hugo site in $DEST..."
    echo ""
    
    cd "$DEST"
    if hugo; then
        print_success "Hugo site built successfully"
        print_info "Output location: $DEST/public"
    else
        print_error "Hugo build failed"
        exit 1
    fi
elif [ "$DO_SYNC" = "true" ] && [ "$DRY_RUN" != "true" ]; then
    # If we synced but didn't ask to build, show instructions
    print_step "Step 3: Build Hugo site (optional)"
    print_info "You can now build the Hugo site:"
    echo -e "  ${BLUE}cd $DEST${NC}"
    echo -e "  ${BLUE}hugo${NC}"
    echo ""
fi

# Done
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Pipeline completed successfully!                         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
