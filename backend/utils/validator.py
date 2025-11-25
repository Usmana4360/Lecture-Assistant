import requests
from bs4 import BeautifulSoup
from typing import Dict, Optional


def fetch_with_beautifulsoup(url: str, timeout: int = 10) -> Optional[str]:
    """
    Lightweight URL fetching with graceful failure
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ResearchBot/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        
        if response.status_code != 200:
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
            
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Limit to prevent token overflow
        return text[:5000]
        
    except Exception as e:
        print(f"Error fetching {url}: {str(e)}")
        return None


def verify_claim_with_llm(claim: str, source_content: Optional[str], llm) -> Dict:
    """
    Use LLM to verify if source supports claim
    NO SENTENCE-TRANSFORMERS - Pure LLM verification
    """
    if not source_content:
        return {
            "verified": False,
            "reasoning": "Source content could not be retrieved",
            "excerpt": ""
        }
    
    verification_prompt = f"""You are a fact-checker. Analyze if the source supports the claim.

SOURCE CONTENT (truncated):
{source_content[:2000]}

CLAIM:
{claim}

TASK:
1. Does the source content support this claim?
2. If YES: Extract the most relevant excerpt (50-100 words) that supports it
3. If NO: Explain why the claim is not supported

FORMAT:
VERDICT: YES or NO
REASONING: [Your explanation]
EXCERPT: [Relevant text if YES, empty if NO]
"""
    
    try:
        response = llm.invoke(verification_prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Parse response
        verdict = "YES" in response_text[:100].upper()
        
        # Extract excerpt
        excerpt = ""
        if "EXCERPT:" in response_text:
            excerpt_part = response_text.split("EXCERPT:")[1].strip()
            excerpt = excerpt_part[:200]
        
        return {
            "verified": verdict,
            "reasoning": response_text[:300],
            "excerpt": excerpt if verdict else ""
        }
    except Exception as e:
        return {
            "verified": False,
            "reasoning": f"Verification error: {str(e)}",
            "excerpt": ""
        }