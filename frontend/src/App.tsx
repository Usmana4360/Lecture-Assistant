import React, { useState } from 'react';
import axios from 'axios';
import { Play, CheckCircle, XCircle, AlertCircle, Loader2, FileText, Search, CheckSquare, BookOpen } from 'lucide-react';

// API Base URL - CRITICAL: Must match your backend

const API_BASE = "https://lecture-assistant-backend.onrender.com";

// Type definitions
interface ClaimWithSource {
  claim: string;
  source_url: string;
  source_title: string;
  excerpt: string;
  verified: boolean;
  verification_reasoning: string;
  accessed_date: string;
}

interface AgentState {
  topic: string;
  search_queries: string[];
  raw_search_results: Record<string, any>[];
  extracted_claims: ClaimWithSource[];
  draft_plan: string[];
  human_feedback: Record<string, any>;
  refined_plan: string[];
  verified_claims: ClaimWithSource[];
  final_brief: Record<string, any> | null;
  node_logs: Record<string, any>[];
  messages: Record<string, any>[];
  route_to: string;
  refinement_notes: string;
}

interface ResearchSession {
  thread_id: string;
  status: 'running' | 'interrupted' | 'completed' | 'error';
  checkpoint?: string;
  data?: AgentState;
  final_brief?: any;
}

const LectureAssistant: React.FC = () => {
  const [topic, setTopic] = useState('');
  const [session, setSession] = useState<ResearchSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedbackNotes, setFeedbackNotes] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleStartResearch = async () => {
    if (!topic.trim()) {
      setError('Please enter a lecture topic');
      return;
    }

    setLoading(true);
    setError(null);

    console.log('🚀 Starting research for:', topic);
    console.log('📡 API endpoint:', `${API_BASE}/run`);

    try {
      const response = await axios.post(`${API_BASE}/run`, {
        topic: topic
      });

      console.log('✅ Response received:', response.data);

      setSession({
        thread_id: response.data.thread_id,
        status: response.data.status,
        checkpoint: response.data.checkpoint,
        data: response.data.data
      });
    } catch (err: any) {
      console.error('❌ Error:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to start research');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Robust resume helper:
   * - Primary payload: { decision, notes } (matches your backend's FeedbackRequest)
   * - Fallback payload: { response: { decision, notes } } (handles any wrapper-based variants)
   *
   * Ensures notes is always a string and always clears loading in finally block.
   */
  const handlePlanDecision = async (decision: string) => {
    if (!session) return;

    setLoading(true);
    setError(null);

    const notes = feedbackNotes ?? '';
    const primaryPayload = { decision: decision, notes: notes };
    const fallbackPayload = { response: { decision: decision, notes: notes } };

    console.log('🔄 Attempting resume with payload (primary):', primaryPayload);

    try {
      // Try primary format first (matches your backend's FeedbackRequest)
      let response = await axios.post(`${API_BASE}/resume/${session.thread_id}`, primaryPayload, {
        headers: { 'Content-Type': 'application/json' }
      });

      // If server responded but body is unexpected, still validate before using it
      if (!response || !response.data) {
        throw new Error('Empty response from resume endpoint');
      }

      // Apply response safely
      setSession({
        thread_id: response.data.thread_id ?? session.thread_id,
        status: response.data.status ?? (response.data.final_brief ? 'completed' : 'interrupted'),
        checkpoint: response.data.checkpoint,
        data: response.data.data ?? response.data
      });

      // If final brief present, attach it
      if (response.data.final_brief) {
        setSession(prev => prev ? { ...prev, final_brief: response.data.final_brief } : prev);
      }

      setFeedbackNotes('');
      console.log('✅ Resume (primary) success:', response.data);
      return;
    } catch (errPrimary: any) {
      // If validation error (422), try fallback wrapper
      const status = errPrimary?.response?.status;
      console.warn('⚠️ Primary resume failed', errPrimary?.message || errPrimary, 'status=', status);

      if (status === 422 || status === 400) {
        // Try fallback wrapper payload
        try {
          console.log('🔁 Trying fallback payload shape:', fallbackPayload);
          const response = await axios.post(`${API_BASE}/resume/${session.thread_id}`, fallbackPayload, {
            headers: { 'Content-Type': 'application/json' }
          });

          if (!response || !response.data) {
            throw new Error('Empty response from resume endpoint (fallback)');
          }

          setSession({
            thread_id: response.data.thread_id ?? session.thread_id,
            status: response.data.status ?? (response.data.final_brief ? 'completed' : 'interrupted'),
            checkpoint: response.data.checkpoint,
            data: response.data.data ?? response.data
          });

          if (response.data.final_brief) {
            setSession(prev => prev ? { ...prev, final_brief: response.data.final_brief } : prev);
          }

          setFeedbackNotes('');
          console.log('✅ Resume (fallback) success:', response.data);
          return;
        } catch (errFallback: any) {
          console.error('❌ Fallback resume also failed:', errFallback);
          setError(errFallback?.response?.data?.detail || errFallback?.message || 'Failed to resume (fallback)');
        }
      } else {
        // Generic error: show server / network error
        setError(errPrimary?.response?.data?.detail || errPrimary?.message || 'Failed to process decision');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleFactDecision = async (decision: string) => {
    if (!session) return;
    // For fact approval we pass decision directly - reuse handler
    await handlePlanDecision(decision);
  };

  // ========== NEW: PDF DOWNLOAD HANDLER =============== //
  // Only change made: replace JSON download with PDF download using backend endpoint GET /pdf/{thread_id}
  const handleDownloadPDF = async () => {
    if (!session) return;

    try {
      const response = await axios.get(`${API_BASE}/pdf/${session.thread_id}`, {
        responseType: 'blob',
      });

      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = url;
      // Use topic in filename if available
      const safeTopic = session.data?.topic ? session.data.topic.replace(/\s+/g, '-').toLowerCase() : session.thread_id;
      a.download = `research-brief-${safeTopic}.pdf`;
      a.click();

      URL.revokeObjectURL(url);
    } catch (err: any) {
      console.error('❌ PDF download failed', err);
      setError(err.response?.data?.detail || err.message || 'Failed to download PDF');
    }
  };
  // ==================================================== //

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 p-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-3 mb-4">
            <BookOpen className="w-12 h-12 text-blue-600" />
            <h1 className="text-4xl font-bold text-gray-800">Lecture-Assistant Agent</h1>
          </div>
          <p className="text-gray-600">Research, verify, and generate structured lecture briefs with human oversight</p>
        </div>

        {/* API Connection Status */}
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-gray-700">
          <strong>Backend:</strong> {API_BASE}
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
            <p className="text-red-800">{error}</p>
            <button
              onClick={() => setError(null)}
              className="ml-auto text-red-600 hover:text-red-800 font-bold"
            >
              ×
            </button>
          </div>
        )}

        {/* Initial Input */}
        {!session && (
          <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
            <label className="block text-sm font-semibold text-gray-700 mb-3">
              Enter Lecture Topic
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && !loading && handleStartResearch()}
              placeholder="e.g., Machine Learning, Quantum Computing, Blockchain"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              disabled={loading}
            />
            <button
              onClick={handleStartResearch}
              disabled={loading}
              className="mt-4 w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Starting Research...
                </>
              ) : (
                <>
                  <Play className="w-5 h-5" />
                  Start Research
                </>
              )}
            </button>
          </div>
        )}

        {/* Session Progress */}
        {session && (
          <div className="space-y-6">
            {/* Status Card */}
            <div className="bg-white rounded-xl shadow-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${
                    session.status === 'completed' ? 'bg-green-500' :
                    session.status === 'interrupted' ? 'bg-yellow-500' :
                    session.status === 'error' ? 'bg-red-500' : 'bg-blue-500'
                  } animate-pulse`} />
                  <h2 className="text-xl font-bold text-gray-800">
                    Research Session: {session.data?.topic}
                  </h2>
                </div>
                <span className="text-xs text-gray-500 font-mono">
                  {session.thread_id}
                </span>
              </div>

              {/* Progress Indicators */}
              <div className="grid grid-cols-4 gap-4">
                {[
                  { name: 'Search', icon: Search, done: session.data && session.data.raw_search_results.length > 0 },
                  { name: 'Extract', icon: FileText, done: session.data && session.data.extracted_claims.length > 0 },
                  { name: 'Plan Review', icon: CheckSquare, done: session.checkpoint !== 'plan_review' },
                  { name: 'Fact Check', icon: CheckCircle, done: session.status === 'completed' }
                ].map((step, idx) => (
                  <div key={idx} className="flex flex-col items-center">
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center ${
                      step.done ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
                    }`}>
                      <step.icon className="w-6 h-6" />
                    </div>
                    <span className="text-xs text-gray-600 mt-2">{step.name}</span>
                  </div>
                ))}
              </div>

              {/* Debug Info */}
              {session.data && (
                <div className="mt-4 p-3 bg-gray-50 rounded text-xs space-y-1">
                  <div><strong>Searches:</strong> {session.data.search_queries.length}</div>
                  <div><strong>Results:</strong> {session.data.raw_search_results.length}</div>
                  <div><strong>Claims:</strong> {session.data.extracted_claims.length}</div>
                  <div><strong>Verified:</strong> {session.data.verified_claims.length}</div>
                  <div><strong>Plan sections:</strong> {session.data.draft_plan.length}</div>
                </div>
              )}
            </div>

            {/* Plan Review Checkpoint */}
            {session.status === 'interrupted' && session.checkpoint === 'plan_review' && session.data && (
              <div className="bg-white rounded-xl shadow-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <AlertCircle className="w-6 h-6 text-yellow-600" />
                  <h3 className="text-xl font-bold text-gray-800">Review Research Plan</h3>
                </div>

                <div className="bg-gray-50 rounded-lg p-4 mb-4">
                  <h4 className="font-semibold text-gray-700 mb-3">Proposed Outline:</h4>
                  <ol className="space-y-2">
                    {session.data.draft_plan.map((item, idx) => (
                      <li key={idx} className="flex gap-3">
                        <span className="font-bold text-blue-600">{idx + 1}.</span>
                        <span className="text-gray-700">{item}</span>
                      </li>
                    ))}
                  </ol>
                </div>

                <textarea
                  value={feedbackNotes}
                  onChange={(e) => setFeedbackNotes(e.target.value)}
                  placeholder="Add notes, requests, or clarifications..."
                  rows={3}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none mb-4"
                  disabled={loading}
                />

                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => handlePlanDecision('approve')}
                    disabled={loading}
                    className="bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle className="w-5 h-5" />}
                    Approve
                  </button>
                  <button
                    onClick={() => handlePlanDecision('more_sources')}
                    disabled={loading}
                    className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
                    More Sources
                  </button>
                  <button
                    onClick={() => handlePlanDecision('emphasize_topic')}
                    disabled={loading}
                    className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <AlertCircle className="w-5 h-5" />}
                    Adjust Focus
                  </button>
                  <button
                    onClick={() => handlePlanDecision('rework')}
                    disabled={loading}
                    className="bg-orange-600 hover:bg-orange-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <XCircle className="w-5 h-5" />}
                    Rework
                  </button>
                </div>
              </div>
            )}

            {/* Fact Verification Checkpoint */}
            {session.status === 'interrupted' && session.checkpoint === 'fact_verification' && session.data && (
              <div className="bg-white rounded-xl shadow-lg p-6">
                <div className="flex items-center gap-3 mb-4">
                  <CheckCircle className="w-6 h-6 text-blue-600" />
                  <h3 className="text-xl font-bold text-gray-800">Verify Key Claims</h3>
                </div>

                <div className="space-y-4 mb-4">
                  {session.data.verified_claims.slice(0, 6).map((claim, idx) => (
                    <div key={idx} className="bg-gray-50 rounded-lg p-4 border-l-4 border-blue-500">
                      <p className="font-semibold text-gray-800 mb-2">{claim.claim}</p>
                      <div className="text-sm text-gray-600 mb-2">
                        <span className="font-medium">Source:</span>{' '}
                        <a href={claim.source_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
                          {claim.source_title}
                        </a>
                      </div>
                      {claim.excerpt && (
                        <p className="text-sm text-gray-600 italic">"{claim.excerpt.substring(0, 150)}..."</p>
                      )}
                    </div>
                  ))}
                </div>

                <button
                  onClick={() => handleFactDecision('approve_facts')}
                  disabled={loading}
                  className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Generating Brief...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-5 h-5" />
                      Approve & Generate Brief
                    </>
                  )}
                </button>
              </div>
            )}

            {/* Final Brief */}
            {session.status === 'completed' && session.final_brief && (
              <div className="bg-white rounded-xl shadow-lg p-8">
                <div className="flex items-center gap-3 mb-6">
                  <CheckCircle className="w-8 h-8 text-green-600" />
                  <h3 className="text-2xl font-bold text-gray-800">Research Complete!</h3>
                </div>

                <div className="prose max-w-none">
                  <h4 className="text-2xl font-bold text-gray-800 mb-4">{session.final_brief.title}</h4>

                  {/* Introduction */}
                  <div className="mb-6 p-4 bg-blue-50 rounded-lg">
                    <h5 className="font-semibold text-gray-700 mb-2">Introduction</h5>
                    <p className="text-gray-700">{session.final_brief.introduction}</p>
                  </div>

                  {/* Summary */}
                  <div className="mb-6 p-4 bg-gray-50 rounded-lg">
                    <h5 className="font-semibold text-gray-700 mb-2">Executive Summary</h5>
                    <p className="text-gray-700">{session.final_brief.summary}</p>
                  </div>

                  {/* Lecture Plan */}
                  {session.final_brief.lecture_plan && session.final_brief.lecture_plan.length > 0 && (
                    <div className="mb-6">
                      <h5 className="font-semibold text-gray-700 mb-3">📋 Lecture Plan</h5>
                      <ol className="space-y-2 bg-white border border-gray-200 rounded-lg p-4">
                        {session.final_brief.lecture_plan.map((item: string, idx: number) => (
                          <li key={idx} className="flex gap-3">
                            <span className="font-bold text-blue-600 min-w-[24px]">{idx + 1}.</span>
                            <span className="text-gray-700">{item}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {/* Key Findings */}
                  <div className="mb-6">
                    <h5 className="font-semibold text-gray-700 mb-3">🔍 Key Findings</h5>
                    <div className="space-y-3">
                      {session.final_brief.key_findings && session.final_brief.key_findings.map((finding: any, idx: number) => (
                        <div key={idx} className="bg-blue-50 rounded-lg p-4 border-l-4 border-blue-500">
                          <p className="text-gray-800 mb-2">
                            <span className="font-bold text-blue-600">{finding.citation}</span> {finding.finding}
                          </p>
                          {finding.excerpt && (
                            <p className="text-sm text-gray-600 italic mb-2">"{finding.excerpt.substring(0, 150)}..."</p>
                          )}
                          <a
                            href={finding.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sm text-blue-600 hover:underline inline-block"
                          >
                            📄 {finding.source}
                          </a>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Risks */}
                  <div className="mb-6">
                    <h5 className="font-semibold text-gray-700 mb-3">⚠️ Risks and Considerations</h5>
                    <ul className="list-disc list-inside space-y-2 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                      {session.final_brief.risks && session.final_brief.risks.map((risk: string, idx: number) => (
                        <li key={idx} className="text-gray-700">{risk}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Further Reading */}
                  <div className="mb-6">
                    <h5 className="font-semibold text-gray-700 mb-3">📚 Further Reading</h5>
                    <ul className="space-y-2 bg-gray-50 rounded-lg p-4">
                      {session.final_brief.further_reading && session.final_brief.further_reading.map((ref: any, idx: number) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-blue-600 mt-1">•</span>
                          <div>
                            <a
                              href={ref.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline font-medium"
                            >
                              {ref.title}
                            </a>
                            <span className="text-sm text-gray-500 ml-2">(Accessed: {ref.accessed})</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Appendix */}
                  {session.final_brief.appendix && (
                    <div className="mt-8 p-4 bg-gray-100 rounded-lg border border-gray-300">
                      <h5 className="font-semibold text-gray-700 mb-3">📎 Research Metadata</h5>
                      <div className="text-sm text-gray-600 space-y-1">
                        <p><span className="font-medium">Research Date:</span> {session.final_brief.appendix.research_date}</p>
                        <p><span className="font-medium">Sources Analyzed:</span> {session.final_brief.appendix.sources_analyzed}</p>
                        <p><span className="font-medium">Claims Extracted:</span> {session.final_brief.appendix.claims_extracted}</p>
                        <p><span className="font-medium">Claims Verified:</span> {session.final_brief.appendix.claims_verified}</p>
                        <p><span className="font-medium">Execution Trace:</span> {session.final_brief.appendix.node_trace.join(' → ')}</p>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex gap-3 mt-6">
                  <button
                    onClick={() => {
                      setSession(null);
                      setTopic('');
                    }}
                    className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors"
                  >
                    🔄 Start New Research
                  </button>
                  <button
                    onClick={() => {
                      // PDF download replaces JSON download
                      handleDownloadPDF();
                    }}
                    className="flex-1 bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors"
                  >
                    💾 Download PDF
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default LectureAssistant;
