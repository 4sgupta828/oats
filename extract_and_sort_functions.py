
import os
import ast
import pathspec

# Function to calculate complexity (simple example based on number of nodes)
def calculate_complexity(node):
    return len(list(ast.walk(node)))

# Directory to search for Python files
directory = '.'

# List to store function details
functions = []

# Read .gitignore and create a spec object
try:
    with open('.gitignore', 'r') as f:
        spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
except FileNotFoundError:
    spec = None

# Walk through the directory
for root, dirs, files in os.walk(directory):
    if spec:
        # Prune ignored directories in-place to prevent descending into them.
        dirs[:] = [d for d in dirs if not spec.match_file(os.path.join(root, d))]

    for file in files:
        filepath = os.path.join(root, file)
        # Process only files that are not ignored.
        if not spec or not spec.match_file(filepath):
            if file.endswith('.py'):
                with open(filepath, 'r') as f:
                    try:
                        tree = ast.parse(f.read(), filename=filepath)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef):
                                complexity = calculate_complexity(node)
                                functions.append((node.name, complexity, filepath))
                    except SyntaxError:
                        print(f'Syntax error in {filepath}, skipping.')

# Sort functions by complexity
functions.sort(key=lambda x: x[1], reverse=True)

# Write results to a file
with open('function_summary.txt', 'w') as summary:
    for name, complexity, path in functions:
        summary.write(f'{name} (Complexity: {complexity}) in {path}\n')
