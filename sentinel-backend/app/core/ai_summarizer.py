from groq import AsyncGroq
from app.config import settings
from loguru import logger
from typing import Dict, Tuple
import json


class AISummarizer:
    """
    Module 5: AI-Assisted Incident Summary
    Converts structured incident JSON to plain-English ops-bridge-ready summary
    using Groq's LPU inference engine.
    """

    SYSTEM_PROMPT = """You are an operations intelligence assistant for a banking payment system (UBL - United Bank Limited, Pakistan).

Your task is to convert structured incident data into a concise, factual, plain-English incident report suitable for:
- Operations bridge calls
- Incident management tickets  
- Escalation to senior management

Rules:
1. Be factual and concise - maximum 150 words
2. Lead with WHAT happened, then WHERE, then IMPACT
3. Include specific numbers from the provided data
4. End with recommended immediate action
5. Do NOT speculate beyond the provided data
6. Format: Plain paragraphs, no markdown, no bullet points
7. Tone: Professional, urgent, ops-bridge ready
8. Always state: "All figures sourced from Sentinel telemetry"

Begin your response with: "SENTINEL INCIDENT REPORT — Auto-generated [timestamp]" """

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.primary_model = settings.groq_model
        self.fallback_model = settings.groq_fallback_model

    async def generate_summary(self, incident_data: Dict) -> Tuple[str, str]:
        """
        Generate plain-English incident summary.
        Returns (summary_text, model_used)
        """
        user_message = f"""Generate an incident report for the following payment system incident:

{json.dumps(incident_data, indent=2, default=str)}

Produce a concise ops-bridge-ready summary following the system instructions."""

        # Try primary model first, fall back if needed
        for model in [self.primary_model, self.fallback_model]:
            try:
                logger.info(f"Generating AI summary with model: {model}")
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,   # Low temperature for factual, consistent output
                    max_tokens=400,
                    top_p=0.9,
                )
                summary = response.choices[0].message.content.strip()
                logger.info(f"AI summary generated successfully ({len(summary)} chars)")
                return summary, model

            except Exception as e:
                logger.warning(f"Model {model} failed: {e}. Trying fallback...")
                if model == self.fallback_model:
                    logger.error(f"All models failed: {e}")
                    raise

        return "AI summary generation failed. Please review incident data manually.", "none"