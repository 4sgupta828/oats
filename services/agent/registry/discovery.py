# uf_flow/registry/discovery.py

import os
import importlib.util
import inspect
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List
from core.models import UFDescriptor

def discover_ufs_from_directory(path: str) -> List[UFDescriptor]:
    """
    Scans a directory for Python files and discovers functions decorated with @uf.

    Args:
        path: The absolute or relative path to the directory to scan.

    Returns:
        A list of UFDescriptor objects found in the directory.
    """
    descriptors = []
    for root, _, files in os.walk(path):
        for file in files:
            if file.endswith(".py") and file != "__init__.py" and file != "manage.py":
                file_path = os.path.join(root, file)
                
                # Dynamically import the module
                spec = importlib.util.spec_from_file_location(name=f"tools.{file[:-3]}", location=file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Inspect the module for functions with our decorator
                    for _, func in inspect.getmembers(module, inspect.isfunction):
                        if hasattr(func, '_uf_descriptor'):
                            descriptor = getattr(func, '_uf_descriptor')
                            if isinstance(descriptor, UFDescriptor):
                                # Also store the actual callable function for the executor
                                descriptor.callable_func = func
                                descriptors.append(descriptor)
    return descriptors

def discover_ufs_in_file(file_path: str) -> List[UFDescriptor]:
    """
    Scans a single Python file for functions decorated with @uf.

    Args:
        file_path: The absolute or relative path to the Python file to scan.

    Returns:
        A list of UFDescriptor objects found in the file.
    """
    descriptors = []
    
    if not os.path.exists(file_path) or not file_path.endswith(".py"):
        return descriptors
    
    try:
        # Dynamically import the module
        spec = importlib.util.spec_from_file_location(name=f"module_{os.path.basename(file_path)[:-3]}", location=file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Inspect the module for functions with our decorator
            for _, func in inspect.getmembers(module, inspect.isfunction):
                if hasattr(func, '_uf_descriptor'):
                    descriptor = getattr(func, '_uf_descriptor')
                    if isinstance(descriptor, UFDescriptor):
                        # Also store the actual callable function for the executor
                        descriptor.callable_func = func
                        descriptors.append(descriptor)
    except Exception as e:
        print(f"Error discovering UFs in {file_path}: {e}")
    
    return descriptors