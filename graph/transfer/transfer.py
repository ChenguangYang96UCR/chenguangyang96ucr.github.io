import re
import json
from collections import defaultdict

TRIPLE_PATTERN = re.compile(r'\[(.*?);\s*(.*?);\s*(.*?)\]')

# Predicates whose object should be stored as a feature on the subject node
FEATURE_PREDICATES = {
    "latitude",
    "longitude",
    "reviewBody",
    "address",
    "postalCode",
    "description",
}

def make_node_id(value, node_ids):
    if value in node_ids:
        return node_ids[value]
    node_id = f"n{len(node_ids) + 1}"
    node_ids[value] = node_id
    return node_id

def infer_node_type(name):
    if name.startswith("_") or name.startswith("__"):
        return "CodeSet"
    if name.startswith("P-"):
        return "ServicePhone"
    if name.startswith("Ch"):
        return "Review"
    try:
        float(name)
        return "Literal"
    except ValueError:
        pass
    return "Entity"

def clean_label(name):
    if name.startswith("P-"):
        return name[2:]
    return name

def parse_graph_from_text(text):
    node_ids = {}
    nodes = {}
    edges = []
    edge_count = 1

    def ensure_node(raw_name):
        node_id = make_node_id(raw_name, node_ids)
        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "label": clean_label(raw_name),
                "type": infer_node_type(raw_name),
                "description": "",
                "features": {}
            }
        return node_id

    for match in TRIPLE_PATTERN.finditer(text):
        subj_raw, pred, obj_raw = match.groups()
        subj_raw = subj_raw.strip()
        pred = pred.strip()
        obj_raw = obj_raw.strip().strip('"')

        subj_id = ensure_node(subj_raw)

        # If object is a literal or predicate is configured as a feature, save it as a node feature
        is_numeric_literal = False
        try:
            numeric_value = float(obj_raw)
            is_numeric_literal = True
        except ValueError:
            numeric_value = None

        if pred in FEATURE_PREDICATES or is_numeric_literal:
            value = numeric_value if is_numeric_literal else obj_raw
            nodes[subj_id]["features"][pred] = value
            continue

        # Otherwise create object node + edge
        obj_id = ensure_node(obj_raw)
        edges.append({
            "id": f"e{edge_count}",
            "source": subj_id,
            "target": obj_id,
            "label": pred
        })
        edge_count += 1

    return {
        "nodes": nodes,
        "edges": edges
    }

# Example usage:
with open("dataset.txt", "r", encoding="utf-8") as f:
    text = f.read()

GRAPH = parse_graph_from_text(text)

with open("graph.json", "w", encoding="utf-8") as f:
    json.dump(GRAPH, f, indent=2, ensure_ascii=False)

print(json.dumps(GRAPH, indent=2, ensure_ascii=False)[:3000])