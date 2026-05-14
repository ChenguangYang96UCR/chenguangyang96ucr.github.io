import React, { useEffect, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
const API_BASE = "http://40.125.43.67:5000";

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: "20px" }}>
      <h3 style={{ marginBottom: "10px", fontSize: "16px" }}>{title}</h3>
      {children}
    </div>
  );
}

function cleanSummaryText(text) {
  if (!text) return "";

  return text
    .split("\n")
    .map((line) => line.replace(/^#{1,6}\s*/, "").trim())
    .filter((line) => !/^\(?https?:\/\/[^\s]+\)?$/.test(line))
    .join("\n")
    .trim();
}

function Row({ label, value }) {
  const displayValue = Array.isArray(value)
    ? value.join(", ")
    : value === null || value === undefined
    ? ""
    : String(value);

  return (
    <div style={{ display: "flex", marginBottom: "8px" }}>
      <div style={{ width: "120px", color: "#666" }}>{label}</div>
      <div style={{ flex: 1, fontWeight: 500, wordBreak: "break-word" }}>
        {displayValue}
      </div>
    </div>
  );
}

export default function App() {
  const [elements, setElements] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [cy, setCy] = useState(null);
  const [loadingGraph, setLoadingGraph] = useState(true);
  const [loadingNode, setLoadingNode] = useState(false);
  const [error, setError] = useState("");
  const [aiSummary, setAiSummary] = useState("");
  const [aiSources, setAiSources] = useState([]);
  const [loadingAi, setLoadingAi] = useState(false);

  // Load the initial graph from the Flask backend.
  // The backend returns the ServiceType node "Shelter"
  // and all connected Service nodes.
  useEffect(() => {
    async function loadGraph() {
      try {
        setLoadingGraph(true);
        setError("");

        const res = await fetch(`${API_BASE}/api/init`);
        if (!res.ok) {
          throw new Error(`Failed to load graph: ${res.status}`);
        }

        const data = await res.json();
        setElements([...(data.nodes || []), ...(data.edges || [])]);
      } catch (err) {
        console.error(err);
        setError("Failed to load graph from Python backend.");
      } finally {
        setLoadingGraph(false);
      }
    }

    loadGraph();
  }, []);


  async function fetchNodeInfo(nodeId) {
    try {
      setLoadingNode(true);
      setError("");
      setAiSummary("");
      setAiSources([]);
      setLoadingAi(false);

      const encodedNodeId = encodeURIComponent(nodeId);

      // Load node detail and neighbor graph first
      const [nodeRes, graphRes] = await Promise.all([
        fetch(`${API_BASE}/api/node/${encodedNodeId}`),
        fetch(`${API_BASE}/api/node/${encodedNodeId}/neighbors`),
      ]);

      if (!nodeRes.ok) {
        throw new Error(`Failed to load node info: ${nodeRes.status}`);
      }
      if (!graphRes.ok) {
        throw new Error(`Failed to load node subgraph: ${graphRes.status}`);
      }

      const nodeData = await nodeRes.json();
      const graphData = await graphRes.json();

      // Show node details immediately
      setSelectedNode(nodeData);
      setElements([...(graphData.nodes || []), ...(graphData.edges || [])]);

      // Re-layout after graph update
      setTimeout(() => {
        if (cy) {
          cy.layout({
            name: "cose",
            animate: true,
            fit: true,
            padding: 30,
          }).run();
        }
      }, 0);

      // Load AI summary only for Service nodes
      if (nodeData.type === "Service") {
        setLoadingAi(true);

        try {
          const aiRes = await fetch(`${API_BASE}/api/service-ai-summary/${encodedNodeId}`);

          if (!aiRes.ok) {
            throw new Error(`Failed to load AI summary: ${aiRes.status}`);
          }

          const aiData = await aiRes.json();
          setAiSummary(aiData.ai_summary || "");
          setAiSources(aiData.sources || []);
        } catch (aiErr) {
          console.error(aiErr);
          setAiSummary("Failed to generate AI summary.");
        } finally {
          setLoadingAi(false);
        }
      }
    } catch (err) {
      console.error(err);
      setError("Failed to load node details.");
    } finally {
      setLoadingNode(false);
    }
  } 

  // Reset selection and fit current graph into view.
  const resetView = () => {
    if (!cy) return;
    cy.elements().unselect();
    cy.fit(undefined, 40);
    setSelectedNode(null);
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#f8fafc",
        padding: "24px",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.6fr 0.9fr",
          gap: "24px",
          maxWidth: "1400px",
          margin: "0 auto",
        }}
      >
        <div
          style={{
            background: "#fff",
            borderRadius: "16px",
            boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
            padding: "20px",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "16px",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <div>
              <h1 style={{ margin: 0, fontSize: "24px" }}>Graph Explorer</h1>
              <p style={{ margin: "6px 0 0", color: "#666" }}>
                Click a node to load details and its local neighborhood.
              </p>
            </div>

            <button
              onClick={resetView}
              style={{
                padding: "10px 14px",
                borderRadius: "10px",
                border: "1px solid #ccc",
                background: "#fff",
                cursor: "pointer",
              }}
            >
              Reset
            </button>
          </div>

          {error && (
            <div
              style={{
                marginBottom: "12px",
                padding: "10px 12px",
                borderRadius: "10px",
                background: "#fee2e2",
                color: "#991b1b",
              }}
            >
              {error}
            </div>
          )}

          <div
            style={{
              height: "70vh",
              border: "1px solid #e2e8f0",
              borderRadius: "16px",
              overflow: "hidden",
              background: "#fff",
            }}
          >
            {loadingGraph ? (
              <div style={{ padding: "20px", color: "#666" }}>Loading graph...</div>
            ) : (
              <CytoscapeComponent
                elements={elements}
                cy={(instance) => {
                  setCy(instance);

                  // Remove old listeners before adding new ones.
                  instance.removeAllListeners();

                  instance.on("tap", "node", (evt) => {
                    const nodeId = evt.target.id();
                    fetchNodeInfo(nodeId);
                  });

                  instance.on("tap", (evt) => {
                    if (evt.target === instance) {
                      setSelectedNode(null);
                    }
                  });

                  instance.layout({
                    name: "cose",
                    animate: true,
                    fit: true,
                    padding: 30,
                  }).run();
                }}
                style={{ width: "100%", height: "100%" }}
                layout={{ name: "cose", fit: true, padding: 30, animate: true }}
                stylesheet={[
                  // Base style for all nodes
                  {
                    selector: "node",
                    style: {
                      label: "data(label)",
                      "text-valign": "center",
                      "text-halign": "center",
                      color: "#0f172a",
                      "font-size": 12,
                      width: 52,
                      height: 52,
                      "border-width": 2,
                      "border-color": "#ffffff",
                    },
                  },
                  // Service nodes use blue
                  {
                    selector: 'node[type = "Service"]',
                    style: {
                      "background-color": "#93c5fd",
                    },
                  },
                  // ServiceType nodes use red
                  {
                    selector: 'node[type = "ServiceType"]',
                    style: {
                      "background-color": "#fca5a5",
                      width: 62,
                      height: 62,
                      "font-size": 13,
                    },
                  },
                  // Selected node style
                  {
                    selector: "node:selected",
                    style: {
                      "border-width": 4,
                      "border-color": "#0f172a",
                    },
                  },
                  // Edge style
                  {
                    selector: "edge",
                    style: {
                      width: 2,
                      label: "data(label)",
                      "font-size": 10,
                      color: "#64748b",
                      "curve-style": "bezier",
                      "line-color": "#cbd5e1",
                      "target-arrow-color": "#cbd5e1",
                      "target-arrow-shape": "triangle",
                    },
                  },
                ]}
              />
            )}
          </div>
        </div>

        <div
          style={{
            background: "#fff",
            borderRadius: "16px",
            boxShadow: "0 2px 10px rgba(0,0,0,0.06)",
            padding: "20px",
            alignSelf: "start",
          }}
        >
          <h2 style={{ marginTop: 0 }}>Node Details</h2>

          {loadingNode ? (
            <div style={{ color: "#666" }}>Loading node details...</div>
          ) : selectedNode ? (
            <>
              <div style={{ marginBottom: "18px" }}>
                <h3 style={{ margin: "0 0 6px", fontSize: "20px" }}>
                  {selectedNode.label}
                </h3>
                <div style={{ color: "#666" }}>ID: {selectedNode.id}</div>
              </div>

              <Section title="Basic Info">
                <Row label="Type" value={selectedNode.type || ""} />
                <Row label="Description" value={selectedNode.description || ""} />
              </Section>

              <Section title="AI Summary">
                {selectedNode?.type !== "Service" ? (
                  <div style={{ color: "#666" }}>
                    AI summary is only available for Service nodes.
                  </div>
                ) : loadingAi ? (
                  <div style={{ color: "#666" }}>Loading summary...</div>
                ) : aiSummary ? (
                  <>
                    <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                      {cleanSummaryText(aiSummary)}
                    </div>

                    {aiSources.length > 0 && (
                      <div style={{ marginTop: "14px" }}>
                        <div style={{ fontWeight: 600, marginBottom: "8px" }}>Sources</div>
                        {aiSources.map((src, idx) => (
                          <div key={idx} style={{ marginBottom: "6px" }}>
                            <a
                              href={src.url}
                              target="_blank"
                              rel="noreferrer"
                              style={{ color: "#2563eb", textDecoration: "none" }}
                            >
                              {src.title || src.url}
                            </a>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ color: "#666" }}>
                    Click a Service node to generate a short summary.
                  </div>
                )}
              </Section>

              <Section title="Features">
                {selectedNode.features &&
                Object.keys(selectedNode.features).length > 0 ? (
                  Object.entries(selectedNode.features).map(([key, value]) => (
                    <Row key={key} label={key} value={value} />
                  ))
                ) : (
                  <div style={{ color: "#666" }}>No extra features.</div>
                )}
              </Section>
            </>
          ) : (
            <div
              style={{
                border: "1px dashed #cbd5e1",
                borderRadius: "16px",
                padding: "40px 20px",
                textAlign: "center",
                color: "#666",
              }}
            >
              Click a node to request details from the Python backend.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}