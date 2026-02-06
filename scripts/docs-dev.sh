#!/bin/bash

# MkDocs Development Helper Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "mkdocs.yml" ]; then
    print_error "mkdocs.yml not found. Please run this script from the repository root."
    exit 1
fi

# Function to install dependencies
install_deps() {
    print_status "Installing MkDocs dependencies with uv..."

    if command -v uv &> /dev/null; then
        uv pip install -r requirements-docs.txt
    elif command -v pip3 &> /dev/null; then
        print_warning "uv not found, falling back to pip3..."
        pip3 install -r requirements-docs.txt
    elif command -v pip &> /dev/null; then
        print_warning "uv not found, falling back to pip..."
        pip install -r requirements-docs.txt
    else
        print_error "Neither uv nor pip found. Please install uv or Python pip first."
        print_status "To install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    print_status "Dependencies installed successfully!"
}

# Function to serve documentation
serve_docs() {
    print_status "Starting MkDocs development server..."
    print_status "Documentation will be available at: http://127.0.0.1:8000"
    print_status "Press Ctrl+C to stop the server"

    mkdocs serve
}

# Function to build documentation
build_docs() {
    print_status "Building static documentation..."

    mkdocs build --clean --strict

    print_status "Documentation built successfully in ./site/"
}

# Function to deploy to GitHub Pages
deploy_docs() {
    print_warning "This will deploy to GitHub Pages. Are you sure? (y/N)"
    read -r response

    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        print_status "Deploying to GitHub Pages..."
        mkdocs gh-deploy
        print_status "Deployed successfully!"
    else
        print_status "Deployment cancelled."
    fi
}

# Function to check documentation
check_docs() {
    print_status "Checking documentation for issues..."

    # Check for broken links
    if command -v mkdocs &> /dev/null; then
        mkdocs build --strict 2>&1 | grep -i "warning\|error" || print_status "No issues found!"
    else
        print_error "MkDocs not installed. Run 'install' first."
    fi
}

# Main script logic
case "${1:-}" in
    "install")
        install_deps
        ;;
    "serve")
        serve_docs
        ;;
    "build")
        build_docs
        ;;
    "deploy")
        deploy_docs
        ;;
    "check")
        check_docs
        ;;
    *)
        echo "MkDocs Development Helper"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  install    Install MkDocs dependencies"
        echo "  serve      Start development server with live reload"
        echo "  build      Build static documentation"
        echo "  deploy     Deploy to GitHub Pages"
        echo "  check      Check documentation for issues"
        echo ""
        echo "Examples:"
        echo "  $0 install    # Install dependencies"
        echo "  $0 serve      # Start development server"
        echo "  $0 build      # Build static site"
        echo ""
        ;;
esac
