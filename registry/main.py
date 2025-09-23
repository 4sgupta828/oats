# uf_flow/registry/main.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List, Optional
from core.models import UFDescriptor, Policy
from registry.discovery import discover_ufs_from_directory

# Generated UFs will be loaded on demand

class Registry:
    """
    An in-memory registry for storing and retrieving UFs and Policies.
    """
    def __init__(self):
        self._ufs: Dict[str, UFDescriptor] = {}
        self._policies: Dict[str, Policy] = {}

    def register_uf(self, descriptor: UFDescriptor):
        """Registers a single Unit of Flow."""
        key = f"{descriptor.name}:{descriptor.version}"
        if key in self._ufs:
            # For simplicity, we'll just overwrite. In a real system, you might error.
            print(f"Warning: Overwriting UF '{key}' in registry.")
        self._ufs[key] = descriptor

    def load_ufs_from_directory(self, path: str):
        """Discovers and registers all UFs from a given directory."""
        descriptors = discover_ufs_from_directory(path)
        for desc in descriptors:
            self.register_uf(desc)

    def get_uf(self, name: str, version: str = "latest") -> Optional[UFDescriptor]:
        """
        Retrieves a UF by name and version.
        
        Note: 'latest' version resolution is not implemented yet.
              Currently requires an exact version match.
        """
        key = f"{name}:{version}"
        return self._ufs.get(key)

    def list_ufs(self) -> List[UFDescriptor]:
        """Returns a list of all registered UFs."""
        return list(self._ufs.values())

    # --- Policy Methods (placeholders for now) ---

    def add_policy(self, policy: Policy):
        self._policies[policy.name] = policy

    def get_policy(self, name: str) -> Optional[Policy]:
        return self._policies.get(name)

# --- Singleton Instance ---
# In our modular monolith, we can use a singleton pattern for easy access.
# When we move to microservices, this will be replaced by a service client.
global_registry = Registry()