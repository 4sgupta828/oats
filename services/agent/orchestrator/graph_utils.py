# uf_flow/orchestrator/graph_utils.py

from typing import List, Dict

def topological_sort(graph: Dict[str, List[str]]) -> List[str]:
    """
    Performs a topological sort on a DAG represented as an adjacency list.

    Args:
        graph: A dictionary where each key is a node ID and the value is a list
               of node IDs it has edges to.

    Returns:
        A list of node IDs in a valid execution order.
        
    Raises:
        ValueError: If the graph contains a cycle or references non-existent nodes.
    """
    # First, collect all nodes mentioned in the graph
    all_nodes = set(graph.keys())
    for edges in graph.values():
        all_nodes.update(edges)
    
    # Initialize in-degree for all nodes
    in_degree = {u: 0 for u in all_nodes}
    
    # Calculate in-degrees
    for u in graph:
        for v in graph[u]:
            if v not in in_degree:
                raise ValueError(f"Graph references non-existent node '{v}'")
            in_degree[v] += 1

    queue = [u for u in all_nodes if in_degree[u] == 0]
    result = []

    while queue:
        u = queue.pop(0)
        result.append(u)
        if u in graph:
            for v in graph[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)

    if len(result) != len(all_nodes):
        raise ValueError("Graph contains a cycle and is not a valid DAG.")

    return result