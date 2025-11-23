#!/usr/bin/env python3
"""
Sync script to copy workspace/output to Hugo site structure.

This script syncs the generated markdown output to the Hugo site with different strategies:
- Replace: Delete destination directory and copy entire source directory
- Merge: Only copy files from source, preserving existing files in destination
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
import yaml
from typing import List, Set


class SyncManager:
    """Manages syncing from workspace output to Hugo site."""
    
    def __init__(self, source_root: Path, dest_root: Path, doc_dirs: List[str], dry_run: bool = False):
        self.source_root = source_root
        self.dest_root = dest_root
        self.doc_dirs = doc_dirs
        self.dry_run = dry_run
        self.stats = {
            'replaced_dirs': 0,
            'merged_dirs': 0,
            'copied_files': 0,
            'deleted_dirs': 0,
            'errors': 0
        }
    
    def log(self, message: str, level: str = 'INFO'):
        """Log a message with level."""
        prefix = '[DRY RUN] ' if self.dry_run else ''
        print(f"{prefix}[{level}] {message}")
    
    def replace_directory(self, src: Path, dst: Path, description: str = ""):
        """
        Replace strategy: Delete destination directory and copy entire source directory.
        
        Args:
            src: Source directory path
            dst: Destination directory path
            description: Optional description for logging
        """
        desc = f" ({description})" if description else ""
        
        if not src.exists():
            self.log(f"Source directory does not exist, skipping{desc}: {src}", "WARNING")
            return
        
        if not src.is_dir():
            self.log(f"Source is not a directory, skipping{desc}: {src}", "WARNING")
            return
        
        self.log(f"Replacing{desc}: {dst}", "INFO")
        
        # Delete destination if it exists
        if dst.exists():
            if not self.dry_run:
                try:
                    shutil.rmtree(dst)
                    self.stats['deleted_dirs'] += 1
                    self.log(f"  Deleted: {dst}", "DEBUG")
                except Exception as e:
                    self.log(f"  Error deleting {dst}: {e}", "ERROR")
                    self.stats['errors'] += 1
                    return
            else:
                self.log(f"  Would delete: {dst}", "DEBUG")
        
        # Copy source to destination
        if not self.dry_run:
            try:
                shutil.copytree(src, dst)
                self.stats['replaced_dirs'] += 1
                self.log(f"  Copied: {src} -> {dst}", "DEBUG")
            except Exception as e:
                self.log(f"  Error copying {src} to {dst}: {e}", "ERROR")
                self.stats['errors'] += 1
        else:
            self.log(f"  Would copy: {src} -> {dst}", "DEBUG")
    
    def merge_directory(self, src: Path, dst: Path, description: str = ""):
        """
        Merge strategy: Only copy files from source, preserving existing files in destination.
        
        Args:
            src: Source directory path
            dst: Destination directory path
            description: Optional description for logging
        """
        desc = f" ({description})" if description else ""
        
        if not src.exists():
            self.log(f"Source directory does not exist, skipping{desc}: {src}", "WARNING")
            return
        
        if not src.is_dir():
            self.log(f"Source is not a directory, skipping{desc}: {src}", "WARNING")
            return
        
        self.log(f"Merging{desc}: {src} -> {dst}", "INFO")
        
        # Create destination if it doesn't exist
        if not dst.exists():
            if not self.dry_run:
                dst.mkdir(parents=True, exist_ok=True)
        
        # Walk through source and copy files
        files_copied = 0
        for src_path in src.rglob('*'):
            if src_path.is_file():
                # Calculate relative path and destination path
                rel_path = src_path.relative_to(src)
                dst_path = dst / rel_path
                
                # Create parent directories if needed
                if not self.dry_run:
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                if not self.dry_run:
                    try:
                        shutil.copy2(src_path, dst_path)
                        files_copied += 1
                    except Exception as e:
                        self.log(f"  Error copying {src_path} to {dst_path}: {e}", "ERROR")
                        self.stats['errors'] += 1
                else:
                    files_copied += 1
        
        self.stats['merged_dirs'] += 1
        self.stats['copied_files'] += files_copied
        self.log(f"  Merged {files_copied} files", "DEBUG")
    
    def sync_doc_versions(self):
        """Sync all doc version directories using replace strategy."""
        self.log("=" * 80)
        self.log("Syncing doc version directories (REPLACE strategy)")
        self.log("=" * 80)
        
        for doc_dir in self.doc_dirs:
            src = self.source_root / 'content' / 'en' / doc_dir
            dst = self.dest_root / 'content' / 'en' / doc_dir
            self.replace_directory(src, dst, f"doc version {doc_dir}")
    
    def sync_blog_and_community(self):
        """Sync blog and community directories using merge strategy."""
        self.log("=" * 80)
        self.log("Syncing blog and community directories (MERGE strategy)")
        self.log("=" * 80)
        
        for subdir in ['blog', 'community']:
            src = self.source_root / 'content' / 'en' / subdir
            dst = self.dest_root / 'content' / 'en' / subdir
            self.merge_directory(src, dst, subdir)
    
    def sync_data(self):
        """Sync data directory using merge strategy."""
        self.log("=" * 80)
        self.log("Syncing data directory (MERGE strategy)")
        self.log("=" * 80)
        
        src = self.source_root / 'data'
        dst = self.dest_root / 'data'
        self.merge_directory(src, dst, "data")
    
    def sync_static(self):
        """Sync static directory using merge strategy."""
        self.log("=" * 80)
        self.log("Syncing static directory (MERGE strategy)")
        self.log("=" * 80)
        
        src = self.source_root / 'static'
        dst = self.dest_root / 'static'
        self.merge_directory(src, dst, "static")
    
    def run(self):
        """Execute the full sync process."""
        self.log("=" * 80)
        self.log("Starting sync process")
        self.log(f"Source: {self.source_root}")
        self.log(f"Destination: {self.dest_root}")
        self.log(f"Doc dirs: {len(self.doc_dirs)}")
        if self.dry_run:
            self.log("DRY RUN MODE - No changes will be made")
        self.log("=" * 80)
        
        # Verify source exists
        if not self.source_root.exists():
            self.log(f"Source directory does not exist: {self.source_root}", "ERROR")
            sys.exit(1)
        
        # Verify destination exists
        if not self.dest_root.exists():
            self.log(f"Destination directory does not exist: {self.dest_root}", "ERROR")
            sys.exit(1)
        
        # Execute sync operations
        self.sync_doc_versions()
        self.sync_blog_and_community()
        self.sync_data()
        self.sync_static()
        
        # Print summary
        self.log("=" * 80)
        self.log("Sync completed!")
        self.log(f"  Replaced directories: {self.stats['replaced_dirs']}")
        self.log(f"  Merged directories: {self.stats['merged_dirs']}")
        self.log(f"  Copied files: {self.stats['copied_files']}")
        self.log(f"  Deleted directories: {self.stats['deleted_dirs']}")
        self.log(f"  Errors: {self.stats['errors']}")
        self.log("=" * 80)
        
        if self.stats['errors'] > 0:
            sys.exit(1)


def load_doc_dirs(config_path: Path) -> List[str]:
    """Load doc_dirs from process.yaml configuration."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            doc_dirs = config.get('doc_dirs', [])
            print(f"Loaded {len(doc_dirs)} doc directories from configuration")
            return doc_dirs
    except Exception as e:
        print(f"Error loading configuration from {config_path}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Sync workspace output to Hugo site with replace/merge strategies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Sync strategies:
  REPLACE: Delete destination directory and copy entire source directory
  MERGE:   Only copy files from source, preserving existing files in destination

Sync rules:
  - Doc version directories (from process.yaml): REPLACE strategy
  - content/en/blog and content/en/community: MERGE strategy
  - data: MERGE strategy
  - static: MERGE strategy

Examples:
  # Dry run to see what would be synced
  python sync_to_hugo.py --dry-run

  # Sync to default destination
  python sync_to_hugo.py

  # Sync to custom destination
  python sync_to_hugo.py --dest /path/to/hugo/site

  # Use custom config file
  python sync_to_hugo.py --config /path/to/process.yaml
        """
    )
    
    parser.add_argument(
        '--dest',
        type=str,
        default='/Users/hvishwanath/projects/kafka-site',
        help='Destination Hugo site root directory (default: /Users/hvishwanath/projects/kafka-site)'
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default=None,
        help='Source workspace output directory (default: workspace/output relative to script location)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to process.yaml configuration file (default: workspace/process.yaml relative to script)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making any changes'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Determine script directory
    script_dir = Path(__file__).parent.resolve()
    
    # Determine source directory
    if args.source:
        source_root = Path(args.source).resolve()
    else:
        source_root = script_dir / 'workspace' / 'output'
    
    # Determine config file
    if args.config:
        config_path = Path(args.config).resolve()
    else:
        config_path = script_dir / 'workspace' / 'process.yaml'
    
    # Determine destination directory
    dest_root = Path(args.dest).resolve()
    
    # Load doc_dirs from configuration
    doc_dirs = load_doc_dirs(config_path)
    
    # Create sync manager and run
    sync_manager = SyncManager(
        source_root=source_root,
        dest_root=dest_root,
        doc_dirs=doc_dirs,
        dry_run=args.dry_run
    )
    
    sync_manager.run()


if __name__ == '__main__':
    main()

