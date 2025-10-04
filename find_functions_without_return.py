#!/usr/bin/env python3
import os
import ast

# Function to find functions without return statements
def find_functions_without_return(directory):
    functions_without_return = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        tree = ast.parse(f.read(), filename=filepath)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.FunctionDef):
                                if not any(isinstance(n, ast.Return) for n in ast.walk(node)):
                                    functions_without_return.append((filepath, node.name))
                    except (SyntaxError, UnicodeDecodeError):
                        continue
    return functions_without_return

if __name__ == '__main__':
    results = find_functions_without_return('.')
    for filepath, func_name in results:
        print(f"Function '{func_name}' in {filepath} does not have a return statement.")
