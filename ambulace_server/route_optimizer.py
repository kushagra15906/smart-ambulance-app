"""
route_optimizer.py — Multi-Intersection Route Optimizer
=========================================================
Implements A* algorithm on the signal graph.

Cost function per edge:
  cost = distance + α × current_traffic + β × predicted_traffic

Supports both Dijkstra (α only) and A* (with heuristic).
Returns full route with per-node cost breakdown.
"""

import heapq
import math
from typing import Optional

# ── Cost Function Weights ─────────────────────────────────────────────────────

ALPHA = 2.5    # weight for current traffic density
BETA  = 1.8    # weight for predicted traffic (next 2 min)

# ── Graph Definition ──────────────────────────────────────────────────────────
#
# Each entry: signal_id → [(neighbor_id, base_distance_meters)]
# Coordinates are in BASE_COORDS for heuristic calculation

BASE_GRAPH: dict[str, list[tuple[str, float]]] = {
    "HOSPITAL": [("S1", 200)],
    "S1":       [("HOSPITAL", 200), ("S2", 300), ("S4", 250)],
    "S2":       [("S1", 300), ("S3", 280)],
    "S3":       [("S2", 280), ("S6", 350)],
    "S4":       [("S1", 250), ("S5", 220)],
    "S5":       [("S4", 220), ("S6", 200)],
    "S6":       [("S3", 350), ("S5", 200), ("S9", 300)],
    "S7":       [("S8", 180)],
    "S8":       [("S7", 180), ("S9", 240)],
    "S9":       [("S8", 240), ("S6", 300), ("DEST", 150)],
    "DEST":     [("S9", 150)],
}

# GPS coordinates for each node (used in A* heuristic)
BASE_COORDS: dict[str, tuple[float, float]] = {
    "HOSPITAL": (28.6140, 77.2090),
    "S1":       (28.6150, 77.2100),
    "S2":       (28.6160, 77.2130),
    "S3":       (28.6170, 77.2160),
    "S4":       (28.6130, 77.2100),
    "S5":       (28.6130, 77.2120),
    "S6":       (28.6130, 77.2160),
    "S7":       (28.6110, 77.2100),
    "S8":       (28.6110, 77.2130),
    "S9":       (28.6110, 77.2160),
    "DEST":     (28.6100, 77.2180),
}


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    R  = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a  = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _heuristic(node: str, goal: str) -> float:
    """
    A* heuristic: straight-line distance to goal.
    Uses Haversine so it's admissible (never overestimates).
    """
    if node not in BASE_COORDS or goal not in BASE_COORDS:
        return 0.0
    c1, c2 = BASE_COORDS[node], BASE_COORDS[goal]
    return _haversine(c1[0], c1[1], c2[0], c2[1])


def _edge_cost(
    neighbor    : str,
    base_dist   : float,
    signals     : dict,
    predictions : dict,
    alpha       : float = ALPHA,
    beta        : float = BETA,
) -> tuple[float, dict]:
    """
    Compute full cost for traversing one edge.

    Cost = base_distance
         + α × current_traffic_penalty
         + β × predicted_traffic_penalty

    Returns (total_cost, breakdown_dict).
    """
    if neighbor not in signals:
        return base_dist, {
            "distance": base_dist, "traffic_penalty": 0, "predict_penalty": 0}

    current_vc  = signals[neighbor]["vehicle_count"]
    predict_vc  = predictions.get(neighbor, {}).get("predicted", current_vc)

    # Quadratic penalty — heavily penalises critical congestion
    traffic_pen = alpha * (current_vc / 100.0) ** 2 * 500
    predict_pen = beta  * (predict_vc / 100.0) ** 2 * 500

    total = base_dist + traffic_pen + predict_pen

    return total, {
        "distance"       : round(base_dist, 1),
        "current_traffic": current_vc,
        "predicted_traffic": round(predict_vc, 1),
        "traffic_penalty": round(traffic_pen, 1),
        "predict_penalty": round(predict_pen, 1),
        "total_cost"     : round(total, 1),
    }


def astar(
    start       : str,
    end         : str,
    signals     : dict,
    predictions : dict,
    alpha       : float = ALPHA,
    beta        : float = BETA,
) -> tuple[list[str], float, list[dict]]:
    """
    A* shortest path from start → end on the signal graph.

    Parameters:
        start       : starting node ID
        end         : destination node ID
        signals     : current SIGNALS dict from app.py
        predictions : {signal_id: prediction_dict} from TrafficPredictor
        alpha       : weight for current traffic penalty
        beta        : weight for predicted traffic penalty

    Returns:
        (path, total_cost, cost_breakdown_per_hop)
    """
    # Heap entries: (f_score, g_score, node, path, breakdown)
    heap    = [(0.0, 0.0, start, [start], [])]
    visited = {}

    while heap:
        f, g, node, path, breakdown = heapq.heappop(heap)

        if node in visited:
            continue
        visited[node] = g

        if node == end:
            return path, round(g, 2), breakdown

        for neighbor, base_dist in BASE_GRAPH.get(node, []):
            if neighbor in visited:
                continue

            edge_c, edge_bd = _edge_cost(
                neighbor, base_dist, signals, predictions, alpha, beta)

            new_g = g + edge_c
            new_f = new_g + _heuristic(neighbor, end)

            heapq.heappush(heap, (
                new_f, new_g, neighbor,
                path + [neighbor],
                breakdown + [{
                    "from"  : node,
                    "to"    : neighbor,
                    **edge_bd
                }]
            ))

    return [], float("inf"), []


def dijkstra(
    start       : str,
    end         : str,
    signals     : dict,
    predictions : dict,
    alpha       : float = ALPHA,
    beta        : float = BETA,
) -> tuple[list[str], float, list[dict]]:
    """
    Dijkstra fallback (A* without heuristic).
    Use when coordinate data is unreliable.
    """
    heap    = [(0.0, start, [start], [])]
    visited = set()

    while heap:
        g, node, path, breakdown = heapq.heappop(heap)

        if node in visited:
            continue
        visited.add(node)

        if node == end:
            return path, round(g, 2), breakdown

        for neighbor, base_dist in BASE_GRAPH.get(node, []):
            if neighbor in visited:
                continue
            edge_c, edge_bd = _edge_cost(
                neighbor, base_dist, signals, predictions, alpha, beta)
            heapq.heappush(heap, (
                g + edge_c, neighbor,
                path + [neighbor],
                breakdown + [{"from": node, "to": neighbor, **edge_bd}]
            ))

    return [], float("inf"), []


def optimized_route(
    start       : str,
    end         : str,
    signals     : dict,
    predictions : dict,
    use_astar   : bool = True,
    alpha       : float = ALPHA,
    beta        : float = BETA,
) -> dict:
    """
    High-level function: compute best route with full metadata.

    Returns a complete result dict ready for API response.
    """
    if start not in BASE_GRAPH:
        return {"error": f"Unknown start: {start}"}
    if end not in BASE_GRAPH:
        return {"error": f"Unknown end: {end}"}

    fn          = astar if use_astar else dijkstra
    path, cost, breakdown = fn(start, end, signals, predictions, alpha, beta)

    if not path:
        return {"error": "No path found"}

    # Enrich each node with signal + prediction data
    route_detail = []
    for node in path:
        sig  = signals.get(node, {})
        pred = predictions.get(node, {})
        route_detail.append({
            "node"              : node,
            "lat"               : BASE_COORDS.get(node, (0, 0))[0],
            "lon"               : BASE_COORDS.get(node, (0, 0))[1],
            "current_vehicles"  : sig.get("vehicle_count", 0),
            "predicted_vehicles": pred.get("predicted", 0),
            "congestion_now"    : sig.get("congestion", "LOW"),
            "congestion_pred"   : pred.get("congestion", "LOW"),
            "is_green"          : sig.get("is_green", False),
            "confidence"        : pred.get("confidence", 1.0),
        })

    # Find bottleneck (highest predicted traffic on route)
    signal_nodes = [n for n in path if n in signals]
    bottleneck   = None
    if signal_nodes:
        bottleneck = max(
            signal_nodes,
            key=lambda n: predictions.get(n, {}).get("predicted", 0)
        )

    return {
        "algorithm"      : "A*" if use_astar else "Dijkstra",
        "start"          : start,
        "end"            : end,
        "path"           : path,
        "total_cost"     : cost,
        "hop_count"      : len(path),
        "signal_count"   : len(signal_nodes),
        "route_detail"   : route_detail,
        "cost_breakdown" : breakdown,
        "bottleneck"     : bottleneck,
        "alpha"          : alpha,
        "beta"           : beta,
    }