import os
import re
from collections import defaultdict
from py2neo import Graph, Node, NodeMatcher

GRAPH_URI = os.getenv("NEO4J_URI", "http://40.125.43.67:7687")
GRAPH_AUTH = (
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "123456789")
)

GRAPH_DATABASE = os.getenv("NEO4J_DATABASE", "interface")

def get_graph():
    return Graph(
        GRAPH_URI,
        auth=GRAPH_AUTH,
        name=GRAPH_DATABASE
    )

def find_files(directory, filetype="txt"):
    files = []
    sub_paths = []
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(f".{filetype}"):
                files.append(filename)
                sub_paths.append(dirpath)
    return files, sub_paths


def parse_triple_line(line: str):
    line = line.strip()
    if not (line.startswith("[") and line.endswith("]")):
        return None

    line = line[1:-1]
    parts = [p.strip() for p in line.split(";")]
    if len(parts) != 3:
        return None

    return parts[0], parts[1], parts[2]


def parse_time_value(raw_time: str):
    """
    输入示例:
        '"Monday from 08:00 to 17:00"'
        '"Saturday Closed]'
        'Monday from 08:00 to 17:00'
        'Saturday Closed'
    返回:
        ("monday_hours", "08:00-17:00")
        ("saturday_hours", "Closed")
    """
    if raw_time is None:
        return None, None

    text = raw_time.strip()

    # 清洗常见脏字符
    text = text.strip('"').strip("'").strip("]").strip()

    # 处理 Closed
    m_closed = re.match(
        r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+Closed$',
        text,
        re.IGNORECASE
    )
    if m_closed:
        day = m_closed.group(1).lower()
        return f"{day}_hours", "Closed"

    # 处理 from HH:MM to HH:MM
    m_range = re.match(
        r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+from\s+(\d{2}:\d{2})\s+to\s+(\d{2}:\d{2})$',
        text,
        re.IGNORECASE
    )
    if m_range:
        day = m_range.group(1).lower()
        start_time = m_range.group(2)
        end_time = m_range.group(3)
        return f"{day}_hours", f"{start_time}-{end_time}"

    return None, None


def get_or_create_node(graph, label, key, value, extra_props=None):
    matcher = NodeMatcher(graph)
    node = matcher.match(label, **{key: value}).first()

    if node is None:
        props = {key: value}
        if extra_props:
            props.update(extra_props)
        node = Node(label, **props)
        graph.create(node)
    else:
        if extra_props:
            changed = False
            for k, v in extra_props.items():
                if node.get(k) != v:
                    node[k] = v
                    changed = True
            if changed:
                graph.push(node)

    return node


def merge_relationship(graph, start_node, rel_type, end_node):
    query = f"""
    MATCH (a), (b)
    WHERE id(a) = $a_id AND id(b) = $b_id
    MERGE (a)-[r:{rel_type}]->(b)
    """
    graph.run(query, a_id=start_node.identity, b_id=end_node.identity)


def init_service_data():
    return {
        "phone": None,
        "address": None,
        "website": None,
        "description": None,
        "email": None,
        "organization": None,
        "languages": set(),
        "costs": set(),
        "availability": set(),
        "audiences": set(),
        "categories": set(),
        "service_types": set(),
        "ratingValue": None,
        "monday_hours": None,
        "tuesday_hours": None,
        "wednesday_hours": None,
        "thursday_hours": None,
        "friday_hours": None,
        "saturday_hours": None,
        "sunday_hours": None,
    }


def store_triples_into_neo4j(text_file, first_flag=False):
    work_path = os.path.abspath(".") + "/neo4j_store/"
    file_path = os.path.join(work_path, text_file)

    if not os.path.exists(file_path):
        raise ValueError(f"Triples file {file_path} does not exist")

    graph = get_graph()

    if first_flag:
        print("Deleting all existing nodes and relationships...")
        graph.delete_all()

    service_data = defaultdict(init_service_data)

    total_lines = 0
    parsed_triples = 0
    skipped_triples = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            total_lines += 1
            triple = parse_triple_line(raw_line)
            if triple is None:
                continue

            parsed_triples += 1
            subj, pred, obj = triple
            pred = pred.strip()

            if pred == "inCodeSet":
                skipped_triples += 1
                continue

            # skip review
            if pred in {"reviewBody", "reviewAuthor", "reviewRating"}:
                skipped_triples += 1
                continue

            # -----------------------------
            # [value; servicePhone; service_name]
            # -----------------------------
            if pred == "servicePhone":
                service_name = obj
                service_data[service_name]["phone"] = subj

            elif pred == "serviceAddress":
                service_name = obj
                service_data[service_name]["address"] = subj

            elif pred == "serviceWebsite":
                service_name = obj
                service_data[service_name]["website"] = subj

            elif pred == "serviceDescription":
                service_name = obj
                service_data[service_name]["description"] = subj

            elif pred == "serviceEmail":
                service_name = obj
                service_data[service_name]["email"] = subj

            elif pred == "serviceOrganization":
                service_name = obj
                service_data[service_name]["organization"] = subj

            # -----------------------------
            # [service_name; language; Spanish]
            # [service_name; cost; Free]
            # [service_name; availability; Available]
            # [service_name; service type; Food]
            # [service_name; xmlschema11-2#time; "Monday from 08:00 to 17:00"]
            # [service_name; ratingValue; 4.7]
            # -----------------------------
            elif pred == "language":
                service_name = subj
                service_data[service_name]["languages"].add(obj)

            elif pred == "cost":
                service_name = subj
                service_data[service_name]["costs"].add(obj)

            elif pred == "availability":
                service_name = subj
                service_data[service_name]["availability"].add(obj)

            elif pred == "audience":
                service_name = subj
                service_data[service_name]["audiences"].add(obj)

            elif pred == "category":
                service_name = subj
                service_data[service_name]["categories"].add(obj)

            elif pred == "service type":
                service_name = subj
                service_data[service_name]["service_types"].add(obj)

            elif pred == "ratingValue":
                service_name = subj
                try:
                    service_data[service_name]["ratingValue"] = float(obj)
                except ValueError:
                    pass

            elif pred == "xmlschema11-2#time":
                service_name = subj
                day_key, day_value = parse_time_value(obj)
                if day_key is not None:
                    service_data[service_name][day_key] = day_value

            else:
                skipped_triples += 1
                continue

    created_services = 0
    created_types = 0
    created_edges = 0

    seen_type_names = set()

    for service_name, info in service_data.items():
        props = {
            # "phone": info["phone"],
            "address": info["address"],
            "website": info["website"],
            "description": info["description"],
            "email": info["email"],
            "organization": info["organization"],
            "languages": sorted(info["languages"]),
            "costs": sorted(info["costs"]),
            "availability": sorted(info["availability"]),
            "audiences": sorted(info["audiences"]),
            "categories": sorted(info["categories"]),
            "ratingValue": info["ratingValue"],
            "monday_hours": info["monday_hours"],
            "tuesday_hours": info["tuesday_hours"],
            "wednesday_hours": info["wednesday_hours"],
            "thursday_hours": info["thursday_hours"],
            "friday_hours": info["friday_hours"],
            "saturday_hours": info["saturday_hours"],
            "sunday_hours": info["sunday_hours"],
        }

        clean_props = {k: v for k, v in props.items() if v is not None}

        service_node = get_or_create_node(
            graph,
            "Service",
            "name",
            service_name,
            clean_props
        )
        created_services += 1

        for type_name in sorted(info["service_types"]):
            type_node = get_or_create_node(graph, "ServiceType", "name", type_name)
            if type_name not in seen_type_names:
                seen_type_names.add(type_name)
                created_types += 1
            merge_relationship(graph, service_node, "HAS_SERVICE_TYPE", type_node)
            created_edges += 1

    print(f"\nFinished importing: {text_file}")
    print(f"  Total lines read: {total_lines}")
    print(f"  Parsed triples: {parsed_triples}")
    print(f"  Skipped triples: {skipped_triples}")
    print(f"  Service records processed: {created_services}")
    print(f"  Unique ServiceType nodes seen: {created_types}")
    print(f"  HAS_SERVICE_TYPE edges processed: {created_edges}")


def print_graph_summary():
    graph = get_graph()

    print("\n===== Graph Summary =====")

    node_counts = graph.run("""
        MATCH (n)
        RETURN labels(n) AS labels, count(*) AS cnt
        ORDER BY cnt DESC
    """).data()

    print("\nNode counts by label:")
    for row in node_counts:
        print(row)

    rel_counts = graph.run("""
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(*) AS cnt
        ORDER BY cnt DESC
    """).data()

    print("\nRelationship counts by type:")
    for row in rel_counts:
        print(row)

    print("\nSample services:")
    sample_rows = graph.run("""
        MATCH (s:Service)
        OPTIONAL MATCH (s)-[:HAS_SERVICE_TYPE]->(t:ServiceType)
        RETURN s.name AS name,
               s.phone AS phone,
               s.languages AS languages,
               s.costs AS costs,
               s.availability AS availability,
               s.audiences AS audiences,
               s.categories AS categories,
               s.ratingValue AS ratingValue,
               s.monday_hours AS monday_hours,
               s.tuesday_hours AS tuesday_hours,
               s.wednesday_hours AS wednesday_hours,
               s.thursday_hours AS thursday_hours,
               s.friday_hours AS friday_hours,
               s.saturday_hours AS saturday_hours,
               s.sunday_hours AS sunday_hours,
               collect(t.name) AS service_types
        LIMIT 10
    """).data()

    for i, row in enumerate(sample_rows, 1):
        print(f"\n--- Service {i} ---")
        for k, v in row.items():
            print(f"{k}: {v}")

    count_query = """
    MATCH (t:ServiceType)
    RETURN count(t) AS service_type_count
    """
    print("ServiceType count:")
    print(graph.run(count_query).data())

    detail_query = """
    MATCH (s:Service)-[:HAS_SERVICE_TYPE]->(t:ServiceType)
    WITH t.name AS service_type, collect(s.name) AS services
    RETURN service_type, size(services) AS service_count, services[0..10] AS sample_services
    ORDER BY service_count DESC, service_type
    """

    rows = graph.run(detail_query).data()

    for row in rows:
        print("\n---")
        print("service_type:", row["service_type"])
        print("service_count:", row["service_count"])
        print("sample_services:")
        for s in row["sample_services"]:
            print("  ", s)

if __name__ == "__main__":
    work_path = os.path.abspath(".") + "/neo4j_store"
    txt_files, _ = find_files(work_path, filetype="txt")

    if not txt_files:
        print("No txt files found in neo4j_store/")
    else:
        first_flag = True
        for txt_file in txt_files:
            if txt_file != "requirements.txt":
                print(f"Importing {txt_file} into Neo4j...")
                store_triples_into_neo4j(txt_file, first_flag)
                first_flag = False

        print_graph_summary()