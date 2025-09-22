# uf_flow/memory/main.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import List
from core.models import ToolResult

class Memory:
    """
    A simple in-memory store for the agent's experiences.
    
    This is a placeholder for a real vector database.
    """
    def __init__(self):
        self._history: List[ToolResult] = []

    def remember(self, execution_result: ToolResult):
        """Adds an execution result to the agent's memory."""
        print(f"Remembering execution: {execution_result.status}")
        self._history.append(execution_result)

    def query(self, query_text: str, top_k: int = 3) -> List[ToolResult]:
        """
        Performs a basic semantic search over the history.
        
        NOTE: This is a naive implementation. A real implementation would use
              vector embeddings to find semantically similar past results.
        """
        # Naive keyword search for demonstration purposes
        results = [
            res for res in self._history 
            if res.error and query_text.lower() in res.error.lower()
        ]
        return results[:top_k]

# --- Singleton Instance ---
global_memory = Memory()