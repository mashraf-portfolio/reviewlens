"""LangGraph pipeline assembly.

Topology (§2.1):

    plan ──► fetch ──► triage ──┬──► classify ──► cluster ──► quantify
                         ▲      │                                  │
                         │  (not enough data)                      ▼
                         │      │                              diagnose
                         │      │                                  │
                         └──────┘◄── (retry: low quality) ── critique
                                                                   │
                                                                  END

Linear spine:  plan → fetch → triage → classify → cluster → quantify → diagnose → critique

Conditional edges:
  triage   → "classify"  when len(triaged_reviews) >= config.min_n_floor
           → "fetch"     when reviews are insufficient (retry fetch)

  critique → "end"       when report meets quality bar
           → "fetch"     when hallucinations or low confidence detected (retry fetch)

Both retry paths are bounded by:
  - config.max_fetch_loops  (hard loop cap)
  - CostMeter.ceiling_usd   (spend guard — raises BudgetExceeded if exceeded)

TODO: implement build_graph():
  1. Import GraphState from agent.state
  2. Import node functions from agent.nodes
  3. Instantiate StateGraph(GraphState)
  4. Add all 8 nodes: plan, fetch, triage, classify, cluster, quantify, diagnose, critique
  5. Add linear edges: plan→fetch, fetch→triage, classify→cluster,
     cluster→quantify, quantify→diagnose, diagnose→critique
  6. Add conditional edge on triage: route(state) → "classify" | "fetch"
  7. Add conditional edge on critique: route(state) → END | "fetch"
  8. Set entry point to "plan"
  9. Compile and return the graph
  10. Assign to module-level `graph` so callers can do:
        from agent.graph import graph
        result = graph.invoke(initial_state)
"""


def build_graph():
    """Construct and return the compiled LangGraph pipeline.

    TODO: implement — see module docstring for full topology.
    """
    raise NotImplementedError("Graph not yet implemented — see Phase 1")
