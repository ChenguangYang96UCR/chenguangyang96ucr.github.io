from flask import Flask, jsonify
from flask_cors import CORS
from neo4j import GraphDatabase
from openai import OpenAI
import os
import json
import re

app = Flask(__name__)
CORS(app)

# =========================
# Neo4j config
# =========================
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "123456789")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", )

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

# =========================
# OpenAI config
# =========================
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# Helpers
# =========================
def build_node_id(node):
    props = dict(node)
    labels = set(node.labels)
    name = props.get("name", f"neo4j_{node.element_id}")

    if "ServiceType" in labels:
        return f"ServiceType::{name}"
    elif "Service" in labels:
        return f"Service::{name}"
    else:
        return f"Node::{name}"


def parse_node_id(node_id: str):
    if "::" not in node_id:
        return None, None
    prefix, name = node_id.split("::", 1)

    if prefix == "Service":
        return "Service", name
    elif prefix == "ServiceType":
        return "ServiceType", name
    else:
        return None, None


def get_display_label(node):
    props = dict(node)
    return props.get("name", f"neo4j_{node.element_id}")


def get_display_type(node):
    labels = set(node.labels)
    if "ServiceType" in labels:
        return "ServiceType"
    elif "Service" in labels:
        return "Service"
    return "Node"


def make_light_node(node):
    return {
        "data": {
            "id": build_node_id(node),
            "label": get_display_label(node),
            "type": get_display_type(node),
        }
    }


def make_full_node(node):
    props = dict(node)
    return {
        "id": build_node_id(node),
        "label": props.get("name", ""),
        "type": get_display_type(node),
        "description": props.get("description", ""),
        "features": {
            k: v for k, v in props.items()
            if k not in {"name", "description"}
        }
    }


def make_edge_data(rel, source_node, target_node):
    source_id = build_node_id(source_node)
    target_id = build_node_id(target_node)
    rel_type = rel.type

    return {
        "data": {
            "id": f"{source_id}--{rel_type}--{target_id}",
            "source": source_id,
            "target": target_id,
            "label": rel_type
        }
    }

# =========================
# Graph queries
# =========================
def query_service_type_subgraph(service_type_name: str):
    cypher = """
    MATCH (t:ServiceType {name: $type_name})
    OPTIONAL MATCH (s:Service)-[r:HAS_SERVICE_TYPE]->(t)
    RETURN t, r, s
    """

    with driver.session(database="interface") as session:
        records = list(session.run(cypher, type_name=service_type_name))

        if not records:
            return {"nodes": [], "edges": []}

        node_map = {}
        edges = []
        found_type = False

        for record in records:
            t = record["t"]
            r = record["r"]
            s = record["s"]

            if t is not None:
                found_type = True
                tid = build_node_id(t)
                node_map[tid] = make_light_node(t)

            if s is not None:
                sid = build_node_id(s)
                node_map[sid] = make_light_node(s)

            if r is not None and s is not None and t is not None:
                edges.append(make_edge_data(r, s, t))

        if not found_type:
            return {"nodes": [], "edges": []}

        return {
            "nodes": list(node_map.values()),
            "edges": edges
        }


def query_node_detail(node_id: str):
    label, name = parse_node_id(node_id)
    if label is None:
        return None

    cypher = f"""
    MATCH (n:{label} {{name: $name}})
    RETURN n
    LIMIT 1
    """

    with driver.session(database="interface") as session:
        record = session.run(cypher, name=name).single()
        if record is None:
            return None
        return make_full_node(record["n"])


def query_neighbors(node_id: str):
    label, name = parse_node_id(node_id)
    if label is None:
        return {"nodes": [], "edges": []}

    if label == "ServiceType":
        cypher = """
        MATCH (center:ServiceType {name: $name})
        OPTIONAL MATCH (neighbor:Service)-[r:HAS_SERVICE_TYPE]->(center)
        RETURN center, r, neighbor
        """
    elif label == "Service":
        cypher = """
        MATCH (center:Service {name: $name})
        OPTIONAL MATCH (center)-[r:HAS_SERVICE_TYPE]->(neighbor:ServiceType)
        RETURN center, r, neighbor
        """
    else:
        return {"nodes": [], "edges": []}

    with driver.session(database="interface") as session:
        records = list(session.run(cypher, name=name))

        if not records:
            return {"nodes": [], "edges": []}

        node_map = {}
        edges = []
        found_center = False

        for record in records:
            center = record["center"]
            r = record["r"]
            neighbor = record["neighbor"]

            if center is not None:
                found_center = True
                cid = build_node_id(center)
                node_map[cid] = make_light_node(center)

            if neighbor is not None:
                nid = build_node_id(neighbor)
                node_map[nid] = make_light_node(neighbor)

            if r is not None and center is not None and neighbor is not None:
                if label == "ServiceType":
                    edges.append(make_edge_data(r, neighbor, center))
                else:
                    edges.append(make_edge_data(r, center, neighbor))

        if not found_center:
            return {"nodes": [], "edges": []}

        return {
            "nodes": list(node_map.values()),
            "edges": edges
        }


def query_graph(limit_nodes=80):
    cypher = """
    MATCH (s:Service)-[r:HAS_SERVICE_TYPE]->(t:ServiceType)
    RETURN s, r, t
    LIMIT $limit
    """

    with driver.session(database="interface") as session:
        records = list(session.run(cypher, limit=limit_nodes))

        node_map = {}
        edges = []

        for record in records:
            s = record["s"]
            r = record["r"]
            t = record["t"]

            sid = build_node_id(s)
            tid = build_node_id(t)

            node_map[sid] = make_light_node(s)
            node_map[tid] = make_light_node(t)
            edges.append(make_edge_data(r, s, t))

        return {
            "nodes": list(node_map.values()),
            "edges": edges
        }

# =========================
# AI summary helpers
# =========================

def clean_ai_summary(text: str) -> str:
    if not text:
        return ""

    cleaned_lines = []

    for line in text.splitlines():
        line = line.strip()

        # Remove markdown headings like ## Title
        line = re.sub(r"^#{1,6}\s*", "", line)

        # Remove markdown bold markers
        line = line.replace("**", "")

        # Remove a line that is only a URL or wrapped URL
        if re.match(r"^\(?https?://[^\s]+\)?$", line):
            continue

        # Convert markdown link [text](url) -> text
        line = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1", line)

        # Remove bracket-only titles like [Gaudenzia House of Passage]
        line = re.sub(r"^\[([^\]]+)\]$", r"\1", line)

        # Skip empty lines caused by cleanup
        if line:
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip()

    # Collapse 3+ blank lines to at most one blank line
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text

def query_service_detail_for_ai(service_name: str):
    cypher = """
    MATCH (s:Service {name: $name})
    OPTIONAL MATCH (s)-[:HAS_SERVICE_TYPE]->(t:ServiceType)
    RETURN s, collect(t.name) AS service_types
    LIMIT 1
    """

    with driver.session(database="interface") as session:
        record = session.run(cypher, name=service_name).single()
        if record is None:
            return None

        s = record["s"]
        service_types = record["service_types"] or []
        props = dict(s)

        return {
            "name": props.get("name"),
            # "description": props.get("description"),
            "service_types": service_types,
            # "phone": props.get("phone"),
            "address": props.get("address"),
            "website": props.get("website"),
            "serviceUrl": props.get("serviceUrl"),
            "email": props.get("email"),
            "organization": props.get("organization"),
            "languages": props.get("languages", []),
            "costs": props.get("costs", []),
            "availability": props.get("availability", []),
            "audiences": props.get("audiences", []),
            "categories": props.get("categories", []),
            "ratingValue": props.get("ratingValue"),
            "longitude": props.get("longitude"),
            "latitude": props.get("latitude"),
            "monday_hours": props.get("monday_hours"),
            "tuesday_hours": props.get("tuesday_hours"),
            "wednesday_hours": props.get("wednesday_hours"),
            "thursday_hours": props.get("thursday_hours"),
            "friday_hours": props.get("friday_hours"),
            "saturday_hours": props.get("saturday_hours"),
            "sunday_hours": props.get("sunday_hours"),
        }


def call_openai_service_summary(service_data: dict):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    prompt = f"""
You are writing a very short frontend summary for a community service.

Structured service data:
{json.dumps(service_data, ensure_ascii=False, indent=2)}

Requirements:
- Output plain text only.
- Maximum 90 words.
- No markdown.
- No headings.
- No bullet points.
- No links or URLs in the summary text.
- Do not start with the service name as a title.
- Write 1 short paragraph only.
- Include only the most useful details: what the service is, who it may help, cost if known, and hours/availability if known.
- If web search finds a useful fact, blend it into the paragraph briefly.
- If uncertain, be cautious and brief.
Return only the final paragraph.
"""

    response = client.responses.create(
        model="gpt-4.1",
        tools=[{"type": "web_search_preview"}],
        input=prompt,
        include=["web_search_call.action.sources"],
        max_output_tokens=160,
    )

    raw_text = response.output_text.strip()
    summary_text = clean_ai_summary(raw_text)

    sources = []
    output = getattr(response, "output", []) or []
    for item in output:
        if getattr(item, "type", None) == "web_search_call":
            action = getattr(item, "action", None)
            if action and getattr(action, "sources", None):
                for src in action.sources[:4]:
                    sources.append({
                        "title": getattr(src, "title", ""),
                        "url": getattr(src, "url", ""),
                    })

    return {
        "summary": summary_text,
        "sources": sources,
    }

# =========================
# Routes
# =========================
@app.route("/api/graph")
def get_graph():
    data = query_graph(limit_nodes=80)
    return jsonify(data)


@app.route("/api/init")
def get_init():
    try:
        data = query_service_type_subgraph("Shelter")
        return jsonify(data)
    except Exception as e:
        print("ERROR in /api/init:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/node/<path:node_id>")
def get_node(node_id):
    node = query_node_detail(node_id)
    if node is None:
        return jsonify({"error": "Node not found"}), 404
    return jsonify(node)


@app.route("/api/node/<path:node_id>/neighbors")
def get_neighbors(node_id):
    data = query_neighbors(node_id)
    return jsonify(data)


@app.route("/api/service-ai-summary/<path:node_id>")
def get_service_ai_summary(node_id):
    label, name = parse_node_id(node_id)
    if label != "Service":
        return jsonify({"error": "This endpoint only supports Service nodes"}), 400

    service_data = query_service_detail_for_ai(name)
    if service_data is None:
        return jsonify({"error": "Service not found"}), 404

    try:
        result = call_openai_service_summary(service_data)
        return jsonify({
            "service": service_data["name"],
            "ai_summary": result["summary"],
            "sources": result["sources"],
        })
    except Exception as e:
        return jsonify({
            "error": f"Failed to generate AI summary: {str(e)}"
        }), 500


@app.teardown_appcontext
def close_driver(exception=None):
    pass


if __name__ == "__main__":
    app.run(port=5000, debug=True)