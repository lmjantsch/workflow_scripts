#!/usr/bin/env python3

import os
import argparse
import sys

def get_files(path, file_endings=['.py', '.ipynb'], ignore=[]):
    """
    Recursively walks through a directory and collects file contents.

    Args:
        path (str): The starting path (file or directory).
        file_endings (list, optional): List of file extensions to include.
        ignore (list, optional): List of directory/file names to ignore.

    Returns:
        dict or str or None: A nested dictionary representing the directory
        structure and file contents, or the content of a single file, or
        None if the file should be ignored.
    """
    # Check if the current file/directory should be ignored
    if os.path.basename(path) in ignore:
        return None

    # If it's a directory, recurse through its children
    if os.path.isdir(path):
        cache = {}
        for item_name in sorted(os.listdir(path)):
            new_path = os.path.join(path, item_name)
            result = get_files(new_path, file_endings, ignore)
            cache[item_name] = result
        # Return the dictionary only if it's not empty
        return cache

    # If it's a file, check its extension
    if os.path.splitext(path)[-1] in file_endings:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"
            
    # Ignore files that don't match the desired endings
    return None

def create_tree(cache, prefix=""):
    """
    Generates a string representation of the directory tree.
    """
    if not isinstance(cache, dict):
        return ""
        
    tree_str = ""
    entries = sorted(cache.keys())
    for i, key in enumerate(entries):
        is_last = i == (len(entries) - 1)
        connector = "└── " if is_last else "├── "
        tree_str += f"{prefix}{connector}{key}\n"
        
        if isinstance(cache[key], dict):
            new_prefix = prefix + ("    " if is_last else "│   ")
            tree_str += create_tree(cache[key], new_prefix)
            
    return tree_str

def heading(title):
    """
    Creates a formatted heading string.
    """
    h_str = f"#     {title}     #"
    fill_str = "#" * len(h_str)
    return f"\n\n{fill_str}\n{h_str}\n{fill_str}\n"

def create_file_out(cache, key=None):
    """
    Recursively generates a string with the content of all files.
    """
    out_str = ""
    if isinstance(cache, dict):
        for sub_key in sorted(cache.keys()):
            out_str += create_file_out(cache[sub_key], sub_key)
    elif isinstance(cache, str) and key:
        out_str += f"{heading(key)}\n{cache.strip()}\n"
    return out_str

def main():
    """
    Main function to parse arguments and run the project dump.
    """
    parser = argparse.ArgumentParser(
        description="Scans a source directory and compiles the contents of specified file types into a single text file."
    )
    parser.add_argument(
        'source_dir',
        type=str,
        help="The source directory to scan."
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='project_dump.txt',
        help="The name of the output file (default: project_dump.txt)."
    )
    parser.add_argument(
        '-e', '--endings',
        nargs='+',
        default=['.py', '.ipynb', '.md'],
        help="List of file endings to include (e.g., .py .js .html)."
    )
    parser.add_argument(
        '-i', '--ignore',
        nargs='+',
        default=['.git', '__pycache__', '.ipynb_checkpoints'],
        help="List of directories or files to ignore."
    )
    
    args = parser.parse_args()

    src_path = args.source_dir
    basename = os.path.basename(src_path)
    if not basename:
        basename = os.path.basename(os.getcwd())

    if not os.path.exists(src_path):
        print(f"Error: The source path '{src_path}' does not exist.")
        sys.exit(1)

    # Get the file structure and content
    file_cache = {os.path.basename(src_path): get_files(src_path, args.endings, args.ignore)}

    # Handle the case where the source directory is empty or fully ignored
    if not file_cache or not file_cache[os.path.basename(src_path)]:
        print(f"Warning: No files with specified endings found in '{src_path}'. Output file will not be created.")
        return

    # Generate the folder tree string
    tree_str = create_tree(file_cache)
    
    # Generate the combined output string
    output_content = f"{heading('Folder Tree')}\n{tree_str.strip()}\n"
    output_content += create_file_out(file_cache)

    # Write to the output file
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_content)
        print(f"✅ Project dump successfully created at: {args.output}")
    except IOError as e:
        print(f"Error writing to file '{args.output}': {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()