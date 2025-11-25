from backend.models import AgentState, ClaimWithSource
from backend.utils.logger import log_node_execution
from backend.utils.validator import fetch_with_beautifulsoup, verify_claim_with_llm
from backend.utils.prompt_loader import get_prompt # <--- NEW IMPORT
from tavily import TavilyClient
from langchain_openai import ChatOpenAI
from datetime import datetime
import os
import json
import re
import sys
from dotenv import load_dotenv
from pathlib import Path
from typing import Dict, List

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


dotenv_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path, override=True)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
TAVILY_KEY = os.getenv("TAVILY_API_KEY")
MODEL_CONFIG = {
    "model": MODEL,
    "temperature": 0,
    "provider": "OpenAI"
}

print(f"[INIT] OpenAI Key: {'✅' if OPENAI_KEY else '❌'}", flush=True)
print(f"[INIT] Tavily Key: {'✅' if TAVILY_KEY else '❌'}", flush=True)
print(f"[INIT] Model: {MODEL}", flush=True)

if not OPENAI_KEY or not TAVILY_KEY:
    raise ValueError("Missing API keys!")

# Initialize clients
tavily_client = TavilyClient(api_key=TAVILY_KEY)
llm = ChatOpenAI(model=MODEL, api_key=OPENAI_KEY, temperature=0)

print("[INIT] Clients initialized successfully", flush=True)


def input_node(state: AgentState) -> AgentState:
    """Parse and validate user's lecture topic"""
    print("\n" + "="*60, flush=True)
    print("NODE: INPUT", flush=True)
    print("="*60, flush=True)
    
    topic = state["topic"]
    print(f"Topic: {topic}", flush=True)
    
    search_queries = [
        f"{topic} comprehensive guide",
        f"{topic} tutorial explained",
        f"{topic} applications examples",
        f"{topic} latest developments 2024",
        f"how does {topic} work"
    ]
    
    state["search_queries"] = search_queries
    print(f"Generated {len(search_queries)} search queries", flush=True)
    
    # LOGGING
    state["node_logs"].append(log_node_execution(
        node_name="input",
        inputs={"topic": topic},
        outputs={"queries_generated": len(search_queries), "examples": search_queries[:2]},
        prompt=None,
        model_config=None # Deterministic node
    ))
    return state


def search_node(state: AgentState) -> AgentState:
    """Perform web search using Tavily API"""
    print("\n" + "="*60, flush=True)
    print("NODE: SEARCH", flush=True)
    print("="*60, flush=True)
    
    results = []
    
    for idx, query in enumerate(state["search_queries"], 1):
        try:
            print(f"[{idx}/{len(state['search_queries'])}] Searching: {query}", flush=True)
            
            search_result = tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=3,
                include_raw_content=True
            )
            
            result_count = len(search_result.get("results", []))
            print(f"     Found {result_count} results", flush=True)
            
            for result in search_result.get("results", []):
                results.append({
                    "url": result.get("url"),
                    "title": result.get("title"),
                    "snippet": result.get("content", ""),
                    "raw_content": result.get("raw_content", ""),
                    "score": result.get("score", 0)
                })
        except Exception as e:
            print(f"     ERROR: {str(e)}", flush=True)
    
    print(f"TOTAL RESULTS: {len(results)}", flush=True)
    state["raw_search_results"] = results
    
    # LOGGING
    state["node_logs"].append(log_node_execution(
        node_name="search",
        inputs={"queries": state["search_queries"]},
        outputs={"total_results": len(results)},
        prompt=None,
        model_config={"tool": "Tavily API"}
    ))
    
    return state


def extract_node(state: AgentState) -> AgentState:
    """Extract claims from search results using LLM"""
    print("\n" + "="*60, flush=True)
    print("NODE: EXTRACT", flush=True)
    print("="*60, flush=True)
    
    if not state["raw_search_results"]:
        print("ERROR: No search results to extract from!", flush=True)
        state["extracted_claims"] = []
        return state
    
    # Build context
    sources_context = []
    for idx, result in enumerate(state["raw_search_results"][:10], 1):
        content = result.get('raw_content', result.get('snippet', ''))[:1000]
        sources_context.append(f"""SOURCE {idx}:
Title: {result['title']}
URL: {result['url']}
Content: {content}
---""")
    
    context = "\n\n".join(sources_context)
    
    # --- PROMPT REPLACEMENT START ---
    extraction_prompt = get_prompt("extract").format(
        topic=state['topic'],
        context=context
    )
    # --- PROMPT REPLACEMENT END ---
    
    try:
        print("Calling OpenAI API...", flush=True)
        response = llm.invoke(extraction_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        print(f"Response length: {len(response_text)} chars", flush=True)
        print(f"Response preview: {response_text[:150]}...", flush=True)
        
        # Clean response
        response_text = response_text.strip()
        response_text = re.sub(r'```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```', '', response_text)
        
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        print("Parsing JSON...", flush=True)
        claims_data = json.loads(response_text)
        
        if not isinstance(claims_data, list):
            raise ValueError("Response is not a JSON array")
        
        print(f"Parsed {len(claims_data)} claims from JSON", flush=True)
        
        claims = []
        for idx, claim_dict in enumerate(claims_data[:10], 1):
            claim_text = claim_dict.get("claim", "").strip()
            source_url = claim_dict.get("source_url", "").strip()
            
            if claim_text and source_url and len(claim_text) > 20:
                claim_obj = ClaimWithSource(
                    claim=claim_text,
                    source_url=source_url,
                    source_title=claim_dict.get("source_title", "").strip(),
                    excerpt=claim_dict.get("excerpt", "").strip()[:400],
                    verified=False,
                    verification_reasoning="Not yet verified",
                    accessed_date=datetime.now().isoformat()
                )
                claims.append(claim_obj)
                print(f"   [{idx}] {claim_text[:60]}...", flush=True)
        
        print(f"EXTRACTED {len(claims)} VALID CLAIMS", flush=True)
        state["extracted_claims"] = claims
        
    except json.JSONDecodeError as e:
        print(f"JSON ERROR: {str(e)}", flush=True)
        print(f"Raw response: {response_text[:500]}", flush=True)
        state["extracted_claims"] = []
    except Exception as e:
        print(f"EXTRACTION ERROR: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        state["extracted_claims"] = []
    
    # LOGGING
    state["node_logs"].append(log_node_execution(
        node_name="extract",
        inputs={"source_count": len(state["raw_search_results"])},
        outputs={"claims_extracted": len(state["extracted_claims"])},
        prompt=extraction_prompt,  # Capturing the full prompt
        model_config=MODEL_CONFIG
    ))
    
    return state


def author_prioritization_node(state: AgentState) -> AgentState:
    """Prioritize authoritative sources"""
    print("\n" + "="*60, flush=True)
    print("NODE: PRIORITIZE", flush=True)
    print("="*60, flush=True)
    
    authoritative_domains = [
        ".edu", ".gov", ".org", "arxiv.org", "ieee.org", "acm.org",
        "nature.com", "sciencedirect.com", "springer.com",
        "wikipedia.org", "research.", "scholar."
    ]
    
    prioritized_claims = []
    regular_claims = []
    
    for claim in state["extracted_claims"]:
        is_authoritative = any(domain in claim.source_url.lower() for domain in authoritative_domains)
        if is_authoritative:
            prioritized_claims.append(claim)
        else:
            regular_claims.append(claim)
    
    state["extracted_claims"] = prioritized_claims + regular_claims
    
    print(f"Prioritized: {len(prioritized_claims)} authoritative, {len(regular_claims)} regular", flush=True)
    
    state["node_logs"].append(log_node_execution(
        "prioritize",
        {"total_claims": len(state["extracted_claims"])},
        {"prioritized": len(prioritized_claims), "regular": len(regular_claims)},
        None
    ))
    
    return state


def verification_node(state: AgentState) -> AgentState:
    """Verify claims against sources"""
    # NOTE: The prompt used in verify_claim_with_llm (in validator.py) must also be moved.
    print("\n" + "="*60, flush=True)
    print("NODE: VERIFY", flush=True)
    print("="*60, flush=True)
    
    verified_claims = []
    claims_to_verify = state["extracted_claims"][:12]
    
    print(f"Verifying {len(claims_to_verify)} claims...", flush=True)
    
    for idx, claim_obj in enumerate(claims_to_verify, 1):
        print(f"[{idx}/{len(claims_to_verify)}] {claim_obj.claim[:50]}...", flush=True)
        
        source_content = None
        
        # Check Tavily raw_content
        for result in state["raw_search_results"]:
            if result["url"] == claim_obj.source_url and result.get("raw_content"):
                source_content = result["raw_content"]
                print(f"     Using Tavily content", flush=True)
                break
        
        # Fallback: fetch
        if not source_content or len(source_content) < 200:
            print(f"     Fetching from URL...", flush=True)
            source_content = fetch_with_beautifulsoup(claim_obj.source_url)
        
        if not source_content:
            print(f"     SKIP: No content", flush=True)
            continue
        
        # Verify with LLM
        verification = verify_claim_with_llm(claim_obj.claim, source_content, llm)
        
        claim_obj.verified = verification["verified"]
        claim_obj.verification_reasoning = verification["reasoning"]
        if verification["excerpt"]:
            claim_obj.excerpt = verification["excerpt"]
        
        if claim_obj.verified:
            verified_claims.append(claim_obj)
            print(f"     VERIFIED ✓", flush=True)
        else:
            print(f"     REJECTED ✗", flush=True)
    
    print(f"VERIFIED: {len(verified_claims)}/{len(claims_to_verify)}", flush=True)
    
    state["verified_claims"] = verified_claims
    state["node_logs"].append(log_node_execution(
        "verify",
        {"total_claims": len(state["extracted_claims"])},
        {"verified": len(verified_claims)},
        None
    ))
    
    return state


def synthesis_node(state: AgentState) -> AgentState:
    """Create lecture plan from verified claims using LLM"""
    print("\n" + "="*60, flush=True)
    print("NODE: SYNTHESIZE", flush=True)
    print("="*60, flush=True)
    
    verified_claims = state["verified_claims"]
    
    if len(verified_claims) < 3:
        print(f"WARNING: Only {len(verified_claims)} verified claims, using fallback", flush=True)
        state["draft_plan"] = [
            f"1. **Fundamentals of {state['topic']}:** Core definitions and scope (10 mins)",
            f"2. **Key Technologies:** Technical architecture and components (15 mins)",
            f"3. **Current Applications:** How {state['topic']} is used in industry (15 mins)",
            f"4. **Critical Analysis:** Limitations and challenges (10 mins)",
            f"5. **Future Outlook:** Emerging trends and research directions (10 mins)"
        ]
        return state
    
    claims_text = "\n".join([f"• {claim.claim}" for claim in verified_claims[:15]])
    
    # --- PROMPT REPLACEMENT START ---
    synthesis_prompt = get_prompt("synthesize").format(
        topic=state['topic'],
        claims_text=claims_text
    )
    # --- PROMPT REPLACEMENT END ---

    try:
        print("Calling OpenAI for synthesis...", flush=True)
        response = llm.invoke(synthesis_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        print(f"Response length: {len(response_text)} chars", flush=True)
        print(f"Response preview: {response_text[:200]}...", flush=True)
        
        # Parse sections - look for numbered lines
        plan = []
        lines = response_text.split('\n')
        
        for line in lines:
            line = line.strip()
            # Match: starts with number followed by dot or paren
            if re.match(r'^\d+[\.\)]\s+\w', line):
                # Remove leading number and whitespace
                cleaned = re.sub(r'^\d+[\.\)]\s+', '', line)
                if len(cleaned) > 15:  # Meaningful section
                    plan.append(cleaned)
                    print(f"     Parsed: {cleaned}", flush=True)
        
        # Validate
        if len(plan) >= 4:
            print(f"✅ GENERATED {len(plan)} SECTIONS", flush=True)
            state["draft_plan"] = plan[:7]  # Max 7 sections
        else:
            print(f"⚠️  Only {len(plan)} sections parsed, using fallback", flush=True)
            raise ValueError(f"Insufficient sections: {len(plan)}")
        
    except Exception as e:
        print(f"SYNTHESIS ERROR: {str(e)}, using fallback", flush=True)
        state["draft_plan"] = [
            f"Introduction: Understanding {state['topic']} (10 minutes)",
            f"Foundations: Core concepts and principles (12 minutes)",
            f"Technical Deep Dive: How {state['topic']} works (15 minutes)",
            f"Real-World Applications: Industry use cases (12 minutes)",
            f"Challenges and Limitations: Current obstacles (8 minutes)",
            f"Future Directions: Emerging trends (8 minutes)"
        ]
    
    state["node_logs"].append(log_node_execution(
        "synthesize",
        {"verified_claims": len(verified_claims)},
        {"plan_sections": len(state["draft_plan"])},
        synthesis_prompt[:300]
    ))
    
    return state


def hitl_plan_review(state: AgentState) -> AgentState:
    """HITL checkpoint - plan review"""
    print("\n" + "="*60, flush=True)
    print("CHECKPOINT: PLAN REVIEW", flush=True)
    print("="*60, flush=True)
    
    state["node_logs"].append(log_node_execution(
        "plan_review",
        {"plan_items": len(state["draft_plan"])},
        {"status": "awaiting_human_review"},
        None
    ))
    
    return state


def refinement_node(state: AgentState) -> AgentState:
    """Refine plan based on feedback"""
    print("\n" + "="*60, flush=True)
    print("NODE: REFINE", flush=True)
    print("="*60, flush=True)
    
    feedback = state.get("human_feedback", {})
    decision = feedback.get("decision", "")
    notes = feedback.get("notes", "").strip()
    
    print(f"Decision: {decision}", flush=True)
    print(f"Notes: {notes if notes else '(none)'}", flush=True)
    
    # APPROVE should NOT reach here - but handle gracefully if it does
    if decision == "approve":
        print("WARNING: Approve reached refinement node - routing to fact_verification", flush=True)
        state["refined_plan"] = state["draft_plan"]
        state["route_to"] = "fact_verification"
        print(f"Route: FACT_VERIFICATION", flush=True)
        
    elif decision == "more_sources":
        # Search for more information
        if notes:
            new_queries = [
                f"{state['topic']} {notes}",
                f"{state['topic']} {notes} detailed",
                f"{state['topic']} {notes} examples"
            ]
        else:
            new_queries = [
                f"{state['topic']} advanced topics",
                f"{state['topic']} detailed guide",
                f"{state['topic']} comprehensive overview"
            ]
        state["search_queries"] = new_queries
        state["route_to"] = "search"
        print(f"New queries: {new_queries}", flush=True)
        print(f"Route: SEARCH", flush=True)
        
    elif decision == "emphasize_topic":
        # Add emphasis section to plan
        if notes:
            emphasis = f"Special Focus: {notes} (15 minutes)"
            state["refined_plan"] = [state["draft_plan"][0]] + [emphasis] + state["draft_plan"][1:]
        else:
            state["refined_plan"] = state["draft_plan"]
        state["route_to"] = "fact_verification"
        print(f"Route: FACT_VERIFICATION", flush=True)
        
    elif decision == "rework":
        # Re-synthesize the plan with notes
        state["refinement_notes"] = notes
        state["route_to"] = "synthesize"
        print(f"Route: SYNTHESIZE", flush=True)
        
    else:  
        # Default: proceed to fact verification
        print(f"UNKNOWN decision: {decision}, defaulting to fact_verification", flush=True)
        state["refined_plan"] = state["draft_plan"]
        state["route_to"] = "fact_verification"
        print(f"Route: FACT_VERIFICATION", flush=True)
    
    state["node_logs"].append(log_node_execution(
        "refine",
        {"decision": decision},
        {"route_to": state["route_to"]},
        None,
        human_decision=feedback
    ))
    
    return state


def hitl_fact_verification(state: AgentState) -> AgentState:
    """HITL checkpoint - fact verification"""
    print("\n" + "="*60, flush=True)
    print("CHECKPOINT: FACT VERIFICATION", flush=True)
    print("="*60, flush=True)
    
    key_claims = state["verified_claims"][:6]
    print(f"Presenting {len(key_claims)} claims for review", flush=True)
    
    state["node_logs"].append(log_node_execution(
        "fact_verification",
        {"claims_presented": len(key_claims)},
        {"status": "awaiting_human_verification"},
        None
    ))
    
    return state


def final_brief_node(state: AgentState) -> AgentState:
    """Generate Final Brief with complete metadata and dynamic risks"""
    print("\n" + "="*60, flush=True)
    print("NODE: FINAL BRIEF", flush=True)
    print("="*60, flush=True)
    
    verified_claims = state["verified_claims"]
    current_plan = state.get("refined_plan") or state["draft_plan"]
    
    # Context for LLM
    claims_text = "\n".join([f"- {c.claim} (Source: {c.source_title})" for c in verified_claims[:25]])
    plan_text = "\n".join(current_plan)
    
    # 1. Generate Detailed Content & Specific Risks
    # --- PROMPT REPLACEMENT START ---
    content_prompt = get_prompt("content").format(
        topic=state['topic'],
        claims_text=claims_text,
        plan_text=plan_text
    )
    # --- PROMPT REPLACEMENT END ---
    
    detailed_content = {}
    try:
        response = llm.invoke(content_prompt)
        text = response.content.replace("```json", "").replace("```", "").strip()
        if "{" in text: 
             text = text[text.find("{"):text.rfind("}")+1]
        detailed_content = json.loads(text)
    except Exception as e:
        print(f"Content Generation Error: {e}")
        # Dynamic fallback that uses the topic name to be less generic
        detailed_content = {
            "executive_summary": f"Overview of {state['topic']}.",
            "sections": [],
            "risks": [
                f"Complexity in implementing {state['topic']}",
                f"Scalability challenges for {state['topic']} systems",
                f"High resource requirements for deployment"
            ]
        }

    # 2. Key Findings (No LLM prompt needed here, uses existing verified claims)
    key_findings = [
        {
            "finding": claim.claim,
            "citation": f"",
            "source": claim.source_title,
            "url": claim.source_url,
            "excerpt": claim.excerpt
        }
        for idx, claim in enumerate(verified_claims[:6])
    ]
    
    # 3. Bibliography
    seen_urls = set()
    bibliography = []
    for claim in verified_claims:
        if claim.source_url not in seen_urls:
            seen_urls.add(claim.source_url)
            # Ensure accessed_date is present before conversion
            accessed_date_str = claim.accessed_date or datetime.now().isoformat()
            
            bibliography.append({
                "title": claim.source_title,
                "url": claim.source_url,
                "accessed": datetime.fromisoformat(accessed_date_str).strftime("%B %d, %Y")
            })

    # 4. Construct Final Brief with RESTORED METADATA
    brief = {
        "title": f"Comprehensive Lecture Plan: {state['topic'].title()}",
        "introduction": f"Generated lecture plan for {state['topic']} based on {len(verified_claims)} verified sources.",
        "summary": detailed_content.get("executive_summary", f"A comprehensive guide to {state['topic']}."),
        "lecture_plan": current_plan, # For frontend list view
        "lecture_sections": detailed_content.get("sections", []), # For PDF detail
        "key_findings": key_findings,
        "risks": detailed_content.get("risks", []),
        "further_reading": bibliography[:10],
        
        # FIXED APPENDIX STRUCTURE (Matches Frontend Expectation)
        "appendix": {
            "node_trace": [log["node"] for log in state["node_logs"]],
            "research_date": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            "sources_analyzed": len(state.get("raw_search_results", [])),
            "claims_extracted": len(state.get("extracted_claims", [])),
            "claims_verified": len(verified_claims)
        }
    }
    
    state["final_brief"] = brief
    
    state["node_logs"].append(log_node_execution(
        node_name="final_brief",
        inputs={"plan_sections": len(current_plan)},
        outputs={"brief_generated": True},
        prompt=content_prompt,
        model_config=MODEL_CONFIG
    ))
    return state