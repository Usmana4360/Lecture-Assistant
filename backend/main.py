from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Optional
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.graph import build_graph
from backend.models import AgentState
import uuid
import os
import sys
import sqlite3
from dotenv import load_dotenv

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

load_dotenv()

app = FastAPI(title="Lecture-Assistant Agent API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("\n" + "="*80, flush=True)
print("INITIALIZING GRAPH", flush=True)
print("="*80 + "\n", flush=True)

# Initialize graph with checkpointing
conn = sqlite3.connect(":memory:", check_same_thread=False)
memory = SqliteSaver(conn)

print("✅ Checkpointer initialized", flush=True)

graph = build_graph()
compiled_graph = graph.compile(
    checkpointer=memory,
    interrupt_before=["plan_review", "fact_verification"]
)

print("✅ Graph compiled successfully", flush=True)
print(f"   Interrupt points: plan_review, fact_verification\n", flush=True)


class ResearchRequest(BaseModel):
    topic: str


class FeedbackRequest(BaseModel):
    decision: str
    notes: Optional[str] = ""

@app.get("/")
def home():
    return {"status": "ok", "message": "Lecture Assistant API is running!"}


@app.post("/run")
async def start_research(request: ResearchRequest):
    """Start new research session"""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n" + "="*80, flush=True)
    print(f"🎬 NEW RESEARCH REQUEST", flush=True)
    print("="*80, flush=True)
    print(f"Thread ID: {thread_id}", flush=True)
    print(f"Topic: {request.topic}", flush=True)
    print("="*80 + "\n", flush=True)
    
    initial_state: AgentState = {
        "topic": request.topic,
        "search_queries": [],
        "raw_search_results": [],
        "extracted_claims": [],
        "draft_plan": [],
        "human_feedback": {},
        "refined_plan": [],
        "verified_claims": [],
        "final_brief": None,
        "node_logs": [],
        "messages": [],
        "route_to": "fact_verification",
        "refinement_notes": ""
    }
    
    print("Initial state created:", flush=True)
    print(f"  - topic: {initial_state['topic']}", flush=True)
    
    try:
        print("\n▶️  INVOKING GRAPH...\n", flush=True)
        
        # Run until first interrupt
        result = compiled_graph.invoke(initial_state, config)
        
        print("\n⏸️  GRAPH INTERRUPTED", flush=True)
        print(f"Result keys: {list(result.keys())}", flush=True)
        print(f"Draft plan items: {len(result.get('draft_plan', []))}", flush=True)
        
        # Get current state to check checkpoint
        state_snapshot = compiled_graph.get_state(config)
        
        checkpoint = state_snapshot.next[0] if state_snapshot.next else "unknown"
        print(f"📍 Checkpoint: {checkpoint}\n", flush=True)
        
        return {
            "thread_id": thread_id,
            "status": "interrupted",
            "checkpoint": checkpoint,
            "data": result
        }
    except Exception as e:
        print(f"\n❌ ERROR in /run:", flush=True)
        print(f"   {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/resume/{thread_id}")
async def resume_research(thread_id: str, feedback: FeedbackRequest):
    """Resume from checkpoint with human feedback - FIXED VERSION"""
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n" + "="*80, flush=True)
    print(f"🔄 RESUME REQUEST", flush=True)
    print("="*80, flush=True)
    print(f"Thread ID: {thread_id}", flush=True)
    print(f"Decision: {feedback.decision}", flush=True)
    print(f"Notes: {feedback.notes if feedback.notes else '(none)'}", flush=True)
    print("="*80 + "\n", flush=True)
    
    try:
        # Get current state
        state_snapshot = compiled_graph.get_state(config)
        
        if not state_snapshot.values:
            print("❌ Session not found", flush=True)
            raise HTTPException(status_code=404, detail="Session not found")
        
        current_checkpoint = state_snapshot.next[0] if state_snapshot.next else 'none'
        print(f"Current checkpoint: {current_checkpoint}", flush=True)
        
        # CRITICAL FIX: Update state with feedback using update_state
        # This modifies the checkpoint WITHOUT restarting the graph
        updated_state = dict(state_snapshot.values)
        updated_state["human_feedback"] = {
            "decision": feedback.decision,
            "notes": feedback.notes,
            "checkpoint": current_checkpoint
        }
        
        print(f"Updating state with feedback: {feedback.decision}", flush=True)
        
        # Update the checkpoint state
        compiled_graph.update_state(config, updated_state)
        
        print("\n▶️  RESUMING GRAPH FROM CHECKPOINT...\n", flush=True)
        
        # CRITICAL: Use invoke with None to resume from checkpoint
        # This continues from where it left off instead of restarting
        result = compiled_graph.invoke(None, config)
        
        print("\n✅ RESUME COMPLETED", flush=True)
        
        # Check if completed or hit another checkpoint
        final_state = compiled_graph.get_state(config)
        
        if final_state.next:
            next_checkpoint = final_state.next[0]
            print(f"\n⏸️  GRAPH INTERRUPTED at {next_checkpoint}\n", flush=True)
            return {
                "thread_id": thread_id,
                "status": "interrupted",
                "checkpoint": next_checkpoint,
                "data": result
            }
        else:
            print("\n✅ GRAPH COMPLETED\n", flush=True)
            return {
                "thread_id": thread_id,
                "status": "completed",
                "final_brief": result.get("final_brief"),
                "data": result
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n❌ ERROR in /resume:", flush=True)
        print(f"   {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{thread_id}")
async def get_status(thread_id: str):
    """Get current execution status"""
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = compiled_graph.get_state(config)
        
        if not state.values:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "thread_id": thread_id,
            "status": "completed" if not state.next else "interrupted",
            "checkpoint": state.next[0] if state.next else None,
            "data": state.values
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail="Session not found")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "lecture-assistant-agent"}

from fastapi.responses import FileResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from datetime import datetime
import os

# In backend/main.py

@app.get("/pdf/{uid}")
async def download_pdf(uid: str):
    try:
        config = {"configurable": {"thread_id": uid}}
        state_snapshot = compiled_graph.get_state(config)

        if not state_snapshot.values:
            raise HTTPException(status_code=404, detail="Session not found")

        # Extract the organized brief from the state
        data = state_snapshot.values
        brief = data.get("final_brief", {})
        
        if not brief:
             raise HTTPException(status_code=404, detail="Final brief not generated yet")

        # PDF Setup
        os.makedirs("temp", exist_ok=True)
        pdf_file = os.path.join("temp", f"lecture_plan_{uid}.pdf")
        doc = SimpleDocTemplate(pdf_file)
        styles = getSampleStyleSheet()
        story = []

        # 1. TITLE
        story.append(Paragraph(f"<b>{brief.get('title', 'Lecture Plan')}</b>", styles["Title"]))
        story.append(Spacer(1, 12))
        
        # 2. INTRODUCTION
        story.append(Paragraph("<b>1. Introduction</b>", styles["Heading2"]))
        story.append(Paragraph(brief.get("introduction", ""), styles["Normal"]))
        story.append(Spacer(1, 12))

        # 3. SUMMARY (Executive Summary)
        story.append(Paragraph("<b>2. Executive Summary</b>", styles["Heading2"]))
        story.append(Paragraph(brief.get("summary", ""), styles["Normal"]))
        story.append(Spacer(1, 12))

        # 4. KEY FINDINGS (With Citations)
        story.append(Paragraph("<b>3. Key Findings</b>", styles["Heading2"]))
        for item in brief.get("key_findings", []):
            text = f"• {item['finding']} <b>{item['citation']}</b>"
            story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 12))

        # 5. COMPREHENSIVE LECTURE SECTIONS
        story.append(Paragraph("<b>4. Detailed Lecture Plan</b>", styles["Heading2"]))
        sections = brief.get("lecture_sections", [])
        
        for idx, section in enumerate(sections, 1):
            # Section Header
            header = f"{idx}. {section.get('heading', 'Section')} ({section.get('duration', '')})"
            story.append(Paragraph(f"<b>{header}</b>", styles["Heading3"]))
            
            # Content
            story.append(Paragraph(section.get("content", ""), styles["Normal"]))
            story.append(Spacer(1, 6))
            
            # Key Points Box
            if section.get("key_points"):
                story.append(Paragraph("<b>Key Learning Points:</b>", styles["Heading4"]))
                for point in section.get("key_points", []):
                    story.append(Paragraph(f"• {point}", styles["Normal"]))
            
            # Teaching Notes
            if section.get("teaching_notes"):
                story.append(Paragraph("<b>Teaching Notes:</b>", styles["Heading4"]))
                for note in section.get("teaching_notes", []):
                    story.append(Paragraph(f"<i>Note: {note}</i>", styles["Normal"]))
            
            story.append(Spacer(1, 12))

        # 6. RISKS
        story.append(Paragraph("<b>5. Risks & Limitations</b>", styles["Heading2"]))
        for risk in brief.get("risks", []):
            story.append(Paragraph(f"• {risk}", styles["Normal"]))
        story.append(Spacer(1, 12))

        # 7. FURTHER READING
        story.append(Paragraph("<b>6. Further Reading / Bibliography</b>", styles["Heading2"]))
        for idx, item in enumerate(brief.get("further_reading", []), 1):
            text = f"[{idx}] {item['title']} <br/><a href='{item['url']}' color='blue'>{item['url']}</a>"
            story.append(Paragraph(text, styles["Normal"]))
            story.append(Spacer(1, 6))

        # 8. APPENDIX (Node Trace)
        story.append(Paragraph("<b>Appendix: System Execution Trace</b>", styles["Heading2"]))
        appendix = brief.get("appendix", {})
        trace = " → ".join(appendix.get("node_trace", []))
        story.append(Paragraph(f"Execution Path: {trace}", styles["Normal"]))
        story.append(Paragraph(f"Total Sources Analyzed: {appendix.get('source_count', 0)}", styles["Normal"]))

        doc.build(story)
        
        return FileResponse(pdf_file, media_type="application/pdf", filename=f"lecture_plan_{uid}.pdf")

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)