#!/usr/bin/env python3

import os
import argparse
import sys
import re
from pathlib import Path
from typing import List, Set, Tuple, Optional, Pattern

# --- Pre-configured Recipes for Different Project Types ---

RECIPES = {
    'default': {
        'ignore': {'.git', '.DS_Store', '.venv', '.gitignore'},
        'exclude': {'.env'},
        'file_endings': {},
    },
    'python': {
        'ignore': {'__pycache__', '.ipynb_checkpoints','.pytest_cache', '/project_dump.txt'},
        'exclude_content': {},
        'file_endings': {'.py', '.ipynb', '.md', '.toml', '.yaml', '.yml'},
    }
}

# --- Core Logic for Parsing .gitignore ---

def parse_gitignore(gitignore_path: Path) -> List[Pattern]:
    """
    Reads a .gitignore file and returns a list of compiled regex patterns.
    """
    if not gitignore_path.is_file():
        return []

    patterns = []
    with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # ignore empty lines or comments
            if not line or line.startswith('#'): 
                continue
            pattern = _translate_to_re_pattern(line.strip())
            if pattern:
                patterns.append(pattern)
    return patterns

# --- Core Logic for converting ignore and exclude items ---

def _translate_to_re_pattern(pattern: str) -> Optional[Pattern]:
    """
    Translates a single gitignore pattern into a compiled regex object.

    Handles basic gitignore syntax like wildcards (*, **), directory matching,
    and anchoring. Does not support negated patterns (!).
    """
    if pattern.startswith('!'):
        print(f"Warning: projectdump currently does not support negated patterns (!)")
        return None

    regex_parts = []
    # If pattern starts with slash it has to match with root directory. Otherwise the pattern can match
    # anywhere in the file string.
    if pattern.startswith('/'):
        regex_parts.append(r'^')
    else:
        regex_parts.append(r'(?:^|\/)')
    pattern = pattern.strip('/')

    # Translate glob-like syntax to regex syntax
    for char in pattern:
        if char == '*':
            # Handle '**' (matches any character, including slashes)
            if regex_parts and regex_parts[-1] == r'[^/]*':
                regex_parts[-1] = r'.*'
            else:
                # Handle '*' (matches any character except slashes)
                regex_parts.append(r'[^/]*')
        elif char == '?':
            regex_parts.append(r'[^/]')  # '?' matches any single character except a slash
        else:
            regex_parts.append(re.escape(char))
    
    # Anchor the regex to match the full file or directory name.
    regex_parts.append(r'(/.*)?$')
    try:
        return re.compile("".join(regex_parts))
    except re.error as e:
        print(f"Warning: Could not compile gitignore pattern '{pattern}'. Error: {e}", file=sys.stderr)
        return None


# --- Core Logic for Discovering and Filtering Files ---

def discover_files(
    root_dir: Path,
    file_endings: Set[str],
    ignore_patterns: Set[Pattern],
    exclude_content_patterns: Set[Pattern],
) -> Tuple[List[Path], List[Path]]:
    """
    Walks a directory and collects all files that meet the criteria.

    This function performs the first pass, discovering and filtering files
    without reading their content, which is more memory-efficient.

    Returns:
        A tuple containing two lists of paths:
        1. Paths whose content should be included.
        2. Paths whose content should be excluded (but are shown in the tree).
    """
    included_paths = []
    excluded_content_paths = []

    for current_path, dirs, files in os.walk(root_dir):
        current_relative_path = Path(current_path).relative_to(root_dir)

        # continue on path that match with ignored patterns
        if any(p.search(str(current_relative_path)) for p in ignore_patterns):
            continue
        
        for item_name in sorted(dirs + files):
            relative_item_path = current_relative_path / item_name

            # 1. Check against ignored patterns
            if any(p.search(str(relative_item_path)) for p in ignore_patterns):
                continue
            
            # 3. Process files
            if relative_item_path.is_file():
                # Check if the file content should be excluded
                if any([p.search(str(relative_item_path)) for p in exclude_content_patterns]):
                    excluded_content_paths.append(relative_item_path)
                    continue

                # Check for valid file endings
                if relative_item_path.suffix in file_endings:
                    included_paths.append(relative_item_path)
                    continue

                excluded_content_paths.append(relative_item_path)

    return sorted(included_paths), sorted(excluded_content_paths)


# --- Output Generation ---

def create_tree(root_dir: Path, all_paths: List[Path]) -> str:
    """
    Generates a string representation of the directory tree from a list of paths.
    """
    tree_str = f"{root_dir.name}\n"
    
    # Create a set of all parent directories for quick lookup
    parents = set()
    for p in all_paths:
        parents.update(p.parents)

    # Use a dictionary to hold the structure
    tree_dict = {}
    for path in all_paths:
        current_level = tree_dict
        for part in path.parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]

    def build_tree_string(subtree: dict, prefix: str = "") -> str:
        """Helper to recursively build the tree string."""
        entries = sorted(subtree.keys())
        output = ""
        for i, key in enumerate(entries):
            is_last = i == (len(entries) - 1)
            connector = "└── " if is_last else "├── "
            output += f"{prefix}{connector}{key}\n"
            
            if subtree[key]:
                new_prefix = prefix + ("    " if is_last else "│   ")
                output += build_tree_string(subtree[key], new_prefix)
        return output

    return tree_str + build_tree_string(tree_dict)

def create_file_content_dump(root_dir: Path, rel_paths: List[Path]) -> str:
    """
    Reads the content of all specified files and combines them into a single string.
    """
    output_parts = []
    
    def heading(title):
        """
        Creates a formatted heading string.
        """
        h_str = f"--- {title} ---"
        return f"\n\n\n\n{h_str}\n"

    for rel_path in rel_paths:
        output_parts.append(heading(str(rel_path)))
        try:
            absolute_path = root_dir / rel_path
            content = absolute_path.read_text(encoding='utf-8', errors='ignore').strip()
            if not content:
                return ''
            output_parts.append(content)
        except Exception as e:
            output_parts.append(f"Error reading file {rel_path}: {e}")
            print(f"Error reading file {rel_path}: {e}")
            
    return "\n".join(output_parts)


# --- Main Execution ---

def main():
    """
    Main function to parse arguments and run the project dump.
    """
    parser = argparse.ArgumentParser(
        description="Scans a source directory and compiles the contents of specified file types into a single text file.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'source_dir',
        type=Path,
        help="The source directory to scan."
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('project_dump.txt'),
        help="The name of the output file (default: project_dump.txt)."
    )
    parser.add_argument(
        '-r', '--recipe',
        type=str,
        choices=RECIPES.keys(),
        help='Use a pre-configured recipe for a specific project type.\n'
             'Available recipes: ' + ', '.join(RECIPES.keys())
    )
    parser.add_argument(
        '-f', '--file-endings',
        nargs='+',
        default=[],
        help="List of file endings to include (e.g., .py .js .html)."
    )
    parser.add_argument(
        '-i', '--ignore',
        nargs='+',
        default=[],
        help="List of directory or file names to completely ignore."
    )
    parser.add_argument(
        '-e', '--exclude-content',
        nargs='+',
        default=[],
        help="List of file names whose content should be excluded (but shown in the tree)."
    )
    parser.add_argument(
        '--no-gitignore',
        action='store_true',
        help="Disable parsing of the .gitignore file."
    )

    parser.add_argument(
        '--no-default',
        action='store_true',
        help="Disable default recipe."
    )

    parser.add_argument(
        '-p', '--print_tree',
        action='store_true',
        help="Print project tree only"
    )
    
    args = parser.parse_args()

    if not args.source_dir.exists():
        print(f"Error: The source path '{args.source_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)
    args.source_dir = args.source_dir.absolute()

    # --- Combine CLI arguments and recipe configurations and ---
    file_endings = set(args.file_endings)
    ignore_items = set(args.ignore)
    exclude_content_items = set(args.exclude_content)

    all_recipes = ['default'] 
    if args.recipe: all_recipes.append(args.recipe)
    for recipe in all_recipes:
        recipe = RECIPES[recipe]
        file_endings.update(recipe.get('file_endings', set()))
        ignore_items.update(recipe.get('ignore', set()))
        exclude_content_items.update(recipe.get('exclude_content', set()))

    # --- Convert ignore_items and exclude_items to re patterns ---
    ignore_patterns = {_translate_to_re_pattern(pattern) for pattern in ignore_items}
    exclude_content_patterns = {_translate_to_re_pattern(pattern) for pattern in exclude_content_items}

    # --- Parse gitignore ---
    gitignore_patterns = []
    if not args.no_gitignore:
        gitignore_path = args.source_dir / '.gitignore'
        print(f"Checking for .gitignore at: {gitignore_path}")
        gitignore_patterns = parse_gitignore(gitignore_path)
        if gitignore_patterns:
            print(f"Found and parsed .gitignore, applying {len(gitignore_patterns)} patterns.")
            exclude_content_patterns.update(gitignore_patterns)

    # --- Pass 1: Discover all relevant files ---
    included_paths, excluded_content_paths = discover_files(
        args.source_dir,
        file_endings,
        ignore_patterns,
        exclude_content_patterns,
    )
    all_tree_paths = sorted(included_paths + excluded_content_paths)

    if not all_tree_paths:
        print("Warning: No files matching the criteria were found. Output file will not be created.")
        return

    # --- Pass 2: Generate the output content ---
    print(f"Found {len(included_paths)} files to include and {len(excluded_content_paths)} to exclude content from.")
    tree_str = create_tree(args.source_dir, all_tree_paths)

    if args.print_tree:
        print(tree_str)
        sys.exit(0)

    content_dump_str = create_file_content_dump(args.source_dir, included_paths)

    # --- Combine and write to file ---
    output_content = (
        f"# Project Dump for: {args.source_dir.resolve().name}\n\n"
        f"## Folder Tree\n\n```\n{tree_str.strip()}\n```\n\n"
        f"## File Contents\n{content_dump_str}"
    )

    try:
        args.output.write_text(output_content, encoding='utf-8')
        print(f"✅ Project dump successfully created at: {args.output}")
    except IOError as e:
        print(f"Error writing to file '{args.output}': {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
