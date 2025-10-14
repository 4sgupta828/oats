import os
import csv
import subprocess
from pathlib import Path

# Workspace root - SECURITY BOUNDARY
WORKSPACE_ROOT = '/Users/sgupta/oats'

def is_within_workspace(filepath):
    """Ensure file operations stay within workspace boundaries"""
    try:
        common = os.path.commonpath([os.path.abspath(filepath), WORKSPACE_ROOT])
        return common == WORKSPACE_ROOT
    except ValueError:
        return False

def get_file_type(filepath):
    try:
        # Use file command to get MIME type
        result = subprocess.run(['file', '--mime-type', filepath], capture_output=True, text=True)
        if result.returncode == 0:
            # Extract just the MIME type from output
            return result.stdout.split(': ')[1].strip()
    except:
        # Fallback to basic extension-based type
        ext = os.path.splitext(filepath)[1].lower()
        if not ext:
            return 'application/octet-stream'
        # Basic MIME type mapping
        mime_types = {
            '.txt': 'text/plain',
            '.log': 'text/plain',
            '.csv': 'text/csv',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
            '.zip': 'application/zip',
            '.gz': 'application/gzip',
            '.tar': 'application/x-tar'
        }
        return mime_types.get(ext, 'application/octet-stream')

def format_size(size_bytes):
    gb = size_bytes / (1024**3)
    if gb >= 1:  # If size is ≥1GB
        return f'{gb:.2f} GB'
    mb = size_bytes / (1024**2)
    return f'{mb:.2f} MB'

def find_large_files(min_size_gb=1):
    # Store results
    files_data = []
    min_bytes = min_size_gb * 1024**3  # Convert GB to bytes
    
    print(f'Scanning for files larger than {min_size_gb}GB...')
    print(f'Workspace root: {WORKSPACE_ROOT}')
    
    # Walk directory tree from workspace root
    for root, _, files in os.walk(WORKSPACE_ROOT):
        for fname in files:
            filepath = os.path.join(root, fname)
            
            # Security check
            if not is_within_workspace(filepath):
                print(f'Warning: Skipping {filepath} - outside workspace')
                continue
                
            try:
                # Get file size
                size = os.path.getsize(filepath)
                
                # Only process files > min_size
                if size > min_bytes:
                    # Get relative path from workspace root
                    rel_path = os.path.relpath(filepath, start=WORKSPACE_ROOT)
                    
                    files_data.append({
                        'path': rel_path,
                        'type': get_file_type(filepath),
                        'size': size,
                        'size_formatted': format_size(size)
                    })
                    print(f'Found large file: {rel_path} ({format_size(size)})')
            except (OSError, IOError) as e:
                print(f'Error processing {filepath}: {e}')
                continue
    
    return files_data

def main():
    # Find all large files (>1GB)
    files = find_large_files(min_size_gb=1)
    
    if not files:
        print('\nNo files larger than 1GB found in workspace.')
        return
    
    # Sort by type
    files.sort(key=lambda x: x['type'])
    
    # Write to CSV
    output_file = 'large_files.csv'
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['path', 'type', 'size_formatted'])
        writer.writeheader()
        for file_data in files:
            writer.writerow({
                'path': file_data['path'],
                'type': file_data['type'],
                'size_formatted': file_data['size_formatted']
            })
    
    print(f'\nFound {len(files)} files larger than 1GB')
    print(f'Results written to {output_file}')
    
    # Print summary of file types found
    type_summary = {}
    for f in files:
        ftype = f['type']
        type_summary[ftype] = type_summary.get(ftype, 0) + 1
    
    print('\nFile type summary:')
    for ftype, count in sorted(type_summary.items()):
        print(f'{ftype}: {count} files')

if __name__ == '__main__':
    main()
