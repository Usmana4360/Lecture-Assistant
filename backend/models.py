from typing import TypedDict, List, Dict, Optional,Any
from pydantic import BaseModel
from datetime import datetime


class ClaimWithSource(BaseModel):
    claim: str
    source_url: str
    source_title: str
    excerpt: str
    verified: bool
    verification_reasoning: str
    accessed_date: str


class AgentState(TypedDict):
    # User input
    topic: str
    
        # Search phase
    search_queries: List[str]
    raw_search_results: List[Dict]

    # Extraction phase
    extracted_claims: List[ClaimWithSource]

    # Planning phase
    draft_plan: List[str]

    # HITL feedback
    human_feedback: Dict[str, Any]

    # Refinement
    refined_plan: List[str]
    verified_claims: List[ClaimWithSource]

    # Output
    final_brief: Optional[Dict]

    # Logging
    node_logs: List[Dict]
    messages: List[Dict]

    # Internal routing logic
    route_to: str
    refinement_notes: str