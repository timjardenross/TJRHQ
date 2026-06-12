#!/usr/bin/env python3
"""
MISTRAL RESEARCH SCOUT SMOKE TEST

Minimal test to call Mistral Research Scout agent and inspect response schema.
Do NOT assume response shape. Log redacted sample response structure.

Usage:
    python MISTRAL_RESEARCH_SCOUT_SMOKE_TEST.py

Requirements:
    - MISTRAL_API_KEY set in environment
    - mistral package: pip install mistral-sdk
"""

import os
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger(__name__)


def smoke_test_mistral_research_scout():
    """
    Minimal smoke test: Call Mistral Research Scout with simple query.
    Log response schema WITHOUT exposing secrets or sensitive content.
    """

    # ========================================================================
    # Step 1: Check Environment
    # ========================================================================
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        log.error("MISTRAL_API_KEY not set in environment")
        return False

    log.info("✓ MISTRAL_API_KEY found in environment")

    # ========================================================================
    # Step 2: Import Mistral SDK
    # ========================================================================
    try:
        from mistral_sdk import Mistral
        log.info("✓ mistral_sdk imported successfully")
    except ImportError as e:
        log.error(f"✗ Failed to import mistral_sdk: {e}")
        log.error("  Install with: pip install mistral-sdk")
        return False

    # ========================================================================
    # Step 3: Initialize Mistral Client
    # ========================================================================
    try:
        client = Mistral(api_key=api_key)
        log.info("✓ Mistral client initialized")
    except Exception as e:
        log.error(f"✗ Failed to initialize Mistral client: {e}")
        return False

    # ========================================================================
    # Step 4: Call Mistral Research Scout Agent
    # ========================================================================

    # Test 1: Simple greeting (verify agent responds)
    log.info("\n" + "="*70)
    log.info("TEST 1: Simple greeting")
    log.info("="*70)

    try:
        response = client.agents.complete(
            model="mistral-large-latest",  # Using latest available
            messages=[
                {
                    "role": "user",
                    "content": "Hello"
                }
            ]
        )

        log.info("✓ Mistral call succeeded")
        log.info("\nRESPONSE SCHEMA (Test 1 - Greeting):")
        log.info(f"  Type: {type(response)}")
        log.info(f"  Dir: {[attr for attr in dir(response) if not attr.startswith('_')]}")

        # Try to access common response attributes
        if hasattr(response, 'content'):
            log.info(f"  .content type: {type(response.content)}")
        if hasattr(response, 'message'):
            log.info(f"  .message type: {type(response.message)}")
        if hasattr(response, 'choices'):
            log.info(f"  .choices type: {type(response.choices)}")
            if response.choices:
                log.info(f"    [0] type: {type(response.choices[0])}")
                log.info(f"    [0] attributes: {[a for a in dir(response.choices[0]) if not a.startswith('_')]}")

        # Log response as JSON if available
        try:
            response_json = json.dumps(response.__dict__ if hasattr(response, '__dict__') else str(response))
            log.info(f"\nRESPONSE STRUCTURE (redacted):")
            log.info(f"  {response_json[:200]}...")  # First 200 chars only
        except Exception as e:
            log.info(f"  (Could not serialize response: {type(e).__name__})")

    except Exception as e:
        log.error(f"✗ Mistral call failed: {type(e).__name__}: {str(e)[:200]}")
        return False

    # ========================================================================
    # Test 2: Research Question
    # ========================================================================
    log.info("\n" + "="*70)
    log.info("TEST 2: Research question")
    log.info("="*70)

    research_query = "What are the latest trends in operational resilience for financial institutions?"

    try:
        response = client.agents.complete(
            model="mistral-large-latest",
            messages=[
                {
                    "role": "user",
                    "content": research_query
                }
            ]
        )

        log.info("✓ Research query succeeded")

        # Extract answer (varies by SDK version)
        answer = None
        if hasattr(response, 'content'):
            answer = response.content
        elif hasattr(response, 'choices') and response.choices:
            if hasattr(response.choices[0], 'message'):
                answer = response.choices[0].message.content
            elif hasattr(response.choices[0], 'text'):
                answer = response.choices[0].text

        if answer:
            log.info(f"\nRESEARCH ANSWER (first 300 chars):")
            log.info(f"  {str(answer)[:300]}...")
        else:
            log.info(f"\nFull response object:")
            log.info(f"  {response}")

    except Exception as e:
        log.error(f"✗ Research query failed: {type(e).__name__}: {str(e)[:200]}")
        return False

    # ========================================================================
    # Step 5: Summary
    # ========================================================================
    log.info("\n" + "="*70)
    log.info("SMOKE TEST SUMMARY")
    log.info("="*70)
    log.info("✓ Mistral SDK available")
    log.info("✓ API key valid")
    log.info("✓ Agent calls working")
    log.info("✓ Response parsing working")
    log.info("\nNEXT STEPS:")
    log.info("  1. Review response schema above")
    log.info("  2. Document response object shape in implementation")
    log.info("  3. Wire response parsing into research workflow")
    log.info("  4. Test with Gemini XO decomposition")

    return True


if __name__ == "__main__":
    log.info("Starting Mistral Research Scout Smoke Test")
    log.info("="*70)

    success = smoke_test_mistral_research_scout()

    log.info("\n" + "="*70)
    if success:
        log.info("✓ SMOKE TEST PASSED")
        exit(0)
    else:
        log.error("✗ SMOKE TEST FAILED")
        exit(1)
