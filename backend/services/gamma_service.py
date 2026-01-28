"""
Gamma API Service
Integration with Gamma.app for AI-powered presentation generation.
"""

import os
import time
import requests
from typing import Dict, Optional, Tuple
from pathlib import Path


class GammaService:
    """
    Service for generating presentations using Gamma API.

    Workflow:
    1. Generate presentation from content/prompt
    2. Poll for completion
    3. Export as PPTX for video conversion
    """

    API_BASE_URL = "https://public-api.gamma.app/v1.0"

    def __init__(self):
        self.api_key = os.getenv("GAMMA_API_KEY")
        self.template_id = os.getenv("GAMMA_TEMPLATE_ID")
        self.theme_id = os.getenv("GAMMA_THEME_ID")

        if not self.api_key:
            raise ValueError("GAMMA_API_KEY not found in environment variables")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def generate_presentation(
        self,
        content: str,
        title: str = "Presentation",
        export_format: Optional[str] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Generate a presentation using Gamma API.

        Args:
            content: Content/prompt for the presentation
            title: Presentation title
            export_format: 'pdf' or 'pptx' to export (None for web only)

        Returns:
            (result_dict, error_message)
            result_dict contains: generationId, url, status, exportUrl (if exported)
        """
        try:
            url = f"{self.API_BASE_URL}/generations/from-template"

            payload = {
                "gammaId": self.template_id,
                "prompt": content,
                "themeId": self.theme_id
            }

            # Add export format if specified
            if export_format in ['pdf', 'pptx']:
                payload["exportAs"] = export_format

            print(f"[Gamma] Generating presentation: {title[:50]}...")
            print(f"[Gamma] Content length: {len(content)} characters")
            print(f"[Gamma] Export format: {export_format or 'web only'}")

            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code in [200, 201]:
                result = response.json()
                print(f"[Gamma] Generation started. ID: {result.get('generationId', 'unknown')}")

                # If we got a generationId, poll for completion
                if 'generationId' in result:
                    return self._poll_for_completion(
                        result['generationId'],
                        export_format=export_format
                    )

                return result, None
            else:
                error = f"Gamma API error {response.status_code}: {response.text}"
                print(f"[Gamma] Error: {error}")
                return None, error

        except requests.Timeout:
            return None, "Gamma API request timed out"
        except Exception as e:
            return None, f"Gamma API error: {str(e)}"

    def _poll_for_completion(
        self,
        generation_id: str,
        export_format: Optional[str] = None,
        max_attempts: int = 60,
        delay: int = 5
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Poll Gamma API until generation is complete.

        Args:
            generation_id: The generation ID to poll
            export_format: Expected export format ('pdf', 'pptx', or None)
            max_attempts: Maximum polling attempts (default 60 = 5 minutes)
            delay: Delay between attempts in seconds

        Returns:
            (result_dict, error_message)
        """
        url = f"{self.API_BASE_URL}/generations/{generation_id}"

        print(f"[Gamma] Polling for completion (max {max_attempts * delay}s)...")

        for attempt in range(max_attempts):
            try:
                response = requests.get(url, headers=self.headers, timeout=10)

                if response.status_code == 200:
                    result = response.json()
                    status = result.get('status', 'unknown')

                    if attempt % 6 == 0:  # Log every 30 seconds
                        print(f"[Gamma] Status: {status} (attempt {attempt + 1}/{max_attempts})")

                    if status == 'completed':
                        print(f"[Gamma] Generation completed!")

                        # Check for export URL if we requested an export
                        if export_format and 'exportUrl' in result:
                            print(f"[Gamma] Export URL available: {result['exportUrl'][:50]}...")
                        elif export_format:
                            print(f"[Gamma] Warning: Export requested but no exportUrl in response")

                        return result, None

                    elif status == 'failed':
                        error = result.get('error', 'Unknown error')
                        print(f"[Gamma] Generation failed: {error}")
                        return None, f"Generation failed: {error}"

                    # Still processing, continue polling

                else:
                    print(f"[Gamma] Poll error: HTTP {response.status_code}")

            except requests.Timeout:
                print(f"[Gamma] Poll timeout, retrying...")
            except Exception as e:
                print(f"[Gamma] Poll error: {e}")

            time.sleep(delay)

        error = f"Timeout after {max_attempts * delay} seconds"
        print(f"[Gamma] {error}")
        return None, error

    def download_export(
        self,
        export_url: str,
        output_path: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Download exported file from Gamma.

        Args:
            export_url: The export URL from Gamma API
            output_path: Local path to save the file

        Returns:
            (success, error_message)
        """
        try:
            print(f"[Gamma] Downloading export from: {export_url[:50]}...")

            # Gamma export URLs might require auth or might be public
            # Try both methods
            response = requests.get(export_url, headers=self.headers, timeout=60, stream=True)

            if response.status_code != 200:
                # Try without auth headers (public URL)
                response = requests.get(export_url, timeout=60, stream=True)

            if response.status_code == 200:
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)

                # Download file
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                file_size = os.path.getsize(output_path)
                print(f"[Gamma] Downloaded {file_size / 1024 / 1024:.2f} MB to {output_path}")
                return True, None
            else:
                error = f"Download failed: HTTP {response.status_code}"
                print(f"[Gamma] {error}")
                return False, error

        except Exception as e:
            error = f"Download error: {str(e)}"
            print(f"[Gamma] {error}")
            return False, error

    def generate_from_documents(
        self,
        documents: list,
        title: str = "Knowledge Base Presentation"
    ) -> str:
        """
        Convert documents to Gamma-friendly presentation content.

        Args:
            documents: List of Document objects
            title: Presentation title

        Returns:
            Formatted content string for Gamma API
        """
        content_parts = [
            f"PRESENTATION TITLE: {title}",
            "",
            "Create a professional business presentation from the following documents:",
            ""
        ]

        # Add document summaries
        for i, doc in enumerate(documents[:20], 1):  # Limit to 20 docs
            doc_title = doc.title or f"Document {i}"
            doc_content = (doc.content or "")[:1000]  # First 1000 chars

            content_parts.append(f"## Document {i}: {doc_title}")
            content_parts.append(doc_content)
            content_parts.append("")

        content_parts.extend([
            "",
            "INSTRUCTIONS:",
            "- Create a cohesive presentation with clear sections",
            "- Use professional business format",
            "- Include key insights and takeaways",
            "- Add relevant data visualizations where appropriate",
            "- Keep slides concise and impactful"
        ])

        return "\n".join(content_parts)

    def generate_from_knowledge_gaps(
        self,
        gaps: list,
        answers: list,
        title: str = "Knowledge Transfer"
    ) -> str:
        """
        Convert knowledge gaps and answers to presentation content.

        Args:
            gaps: List of KnowledgeGap objects
            answers: List of GapAnswer objects
            title: Presentation title

        Returns:
            Formatted content string for Gamma API
        """
        content_parts = [
            f"PRESENTATION TITLE: {title}",
            "SUBTITLE: Critical Knowledge & Answers",
            "",
            "Create a knowledge transfer presentation covering these Q&A pairs:",
            ""
        ]

        # Group answers by gap
        answers_by_gap = {}
        for answer in answers:
            gap_id = answer.knowledge_gap_id
            if gap_id not in answers_by_gap:
                answers_by_gap[gap_id] = []
            answers_by_gap[gap_id].append(answer)

        # Add gaps with answers
        for i, gap in enumerate(gaps[:15], 1):  # Limit to 15 gaps
            content_parts.append(f"## Topic {i}: {gap.title}")
            content_parts.append(f"Category: {gap.category.value}")

            # Add questions and answers
            if gap.id in answers_by_gap:
                for answer in answers_by_gap[gap.id]:
                    q_text = answer.question_text or f"Question {answer.question_index + 1}"
                    a_text = answer.answer_text or "No answer provided"

                    content_parts.append(f"**Q:** {q_text}")
                    content_parts.append(f"**A:** {a_text}")
                    content_parts.append("")
            else:
                # Add questions without answers
                if gap.questions:
                    for q in gap.questions[:3]:  # First 3 questions
                        content_parts.append(f"**Q:** {q}")
                        content_parts.append("")

            content_parts.append("")

        content_parts.extend([
            "",
            "INSTRUCTIONS:",
            "- Organize as a Q&A knowledge base",
            "- Use clear section breaks",
            "- Highlight key insights",
            "- Make it easy to reference later"
        ])

        return "\n".join(content_parts)


# Singleton instance
_gamma_service = None


def get_gamma_service() -> GammaService:
    """Get or create GammaService singleton"""
    global _gamma_service
    if _gamma_service is None:
        _gamma_service = GammaService()
    return _gamma_service
