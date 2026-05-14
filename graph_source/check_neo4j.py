from py2neo import Graph

graph = Graph("bolt://localhost:7687", auth=("neo4j", "123456789"))

GRAPH_URI = "bolt://localhost:7687"
GRAPH_AUTH = ("neo4j", "123456789")

def print_graph_summary():
    graph = Graph(GRAPH_URI, auth=GRAPH_AUTH)

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
    print_graph_summary()