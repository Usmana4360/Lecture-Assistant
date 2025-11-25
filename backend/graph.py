from langgraph.graph import StateGraph, END
from backend.models import AgentState
from backend import nodes

print("[GRAPH] Building workflow...", flush=True)

def build_graph():
    """Construct the LangGraph workflow with proper routing"""
    workflow = StateGraph(AgentState)
    
    # Add all nodes
    print("[GRAPH] Adding nodes...", flush=True)
    workflow.add_node("input", nodes.input_node)
    workflow.add_node("search", nodes.search_node)
    workflow.add_node("extract", nodes.extract_node)
    workflow.add_node("prioritize", nodes.author_prioritization_node)
    workflow.add_node("verify", nodes.verification_node)
    workflow.add_node("synthesize", nodes.synthesis_node)
    workflow.add_node("plan_review", nodes.hitl_plan_review)
    workflow.add_node("refine", nodes.refinement_node)
    workflow.add_node("fact_verification", nodes.hitl_fact_verification)
    workflow.add_node("final_brief", nodes.final_brief_node)
    
    # Define edges
    print("[GRAPH] Adding edges...", flush=True)
    workflow.set_entry_point("input")
    workflow.add_edge("input", "search")
    workflow.add_edge("search", "extract")
    workflow.add_edge("extract", "prioritize")
    workflow.add_edge("prioritize", "verify")
    workflow.add_edge("verify", "synthesize")
    workflow.add_edge("synthesize", "plan_review")
    
    # FIXED: Conditional routing after plan review
    def route_after_plan_review(state):
        """Route after human reviews the plan"""
        decision = state.get("human_feedback", {}).get("decision", "")
        print(f"[ROUTING] Plan review decision: '{decision}'", flush=True)
        
        # APPROVE goes directly to fact verification
        if decision == "approve":
            print(f"[ROUTING] -> Going to fact_verification (APPROVED)", flush=True)
            return "fact_verification"
        # All other decisions need refinement
        else:
            print(f"[ROUTING] -> Going to refine ({decision})", flush=True)
            return "refine"
    
    workflow.add_conditional_edges(
        "plan_review",
        route_after_plan_review,
        {
            "fact_verification": "fact_verification",
            "refine": "refine"
        }
    )
    
    # Dynamic routing from refine node
    def route_after_refine(state):
        """Route based on refinement decision"""
        route_to = state.get("route_to", "fact_verification")
        print(f"[ROUTING] After refine, going to: {route_to}", flush=True)
        return route_to
    
    workflow.add_conditional_edges(
        "refine",
        route_after_refine,
        {
            "search": "search",
            "synthesize": "synthesize",
            "fact_verification": "fact_verification"
        }
    )
    
    workflow.add_edge("fact_verification", "final_brief")
    workflow.add_edge("final_brief", END)
    
    print("[GRAPH] Workflow built successfully", flush=True)
    
    return workflow