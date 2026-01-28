"""
Universal Document Parser Service
Routes documents to the appropriate parser:
- PDF and Images: Azure Document Intelligence
- Office formats (DOCX, PPTX, XLSX, etc.): LlamaParse
"""

import os
import io
import time
import httpx
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# LlamaParse configuration - reload from env each time
def _get_llama_key():
    return os.getenv("LLAMA_CLOUD_API_KEY", "")

LLAMAPARSE_API_URL = "https://api.cloud.llamaindex.ai/api/parsing"

# Azure Document Intelligence configuration - reload from env each time
def _get_azure_config():
    return (
        os.getenv("AZURE_DI_ENDPOINT", ""),
        os.getenv("AZURE_DI_API_KEY", "")
    )


class DocumentParser:
    """
    Universal document parser that routes to the appropriate service:
    - PDF and Images -> Azure Document Intelligence
    - Office formats (DOCX, PPTX, XLSX) -> LlamaParse
    """

    # File extensions handled by Azure Document Intelligence
    AZURE_DI_EXTENSIONS = {
        # PDFs moved to LlamaParse (Azure DI is not configured)
        # ".pdf",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif",
    }

    # File extensions handled by LlamaParse
    LLAMAPARSE_EXTENSIONS = {
        ".pdf",  # Use LlamaParse for PDFs (Azure DI not configured)
        ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
        ".rtf", ".odt", ".ods", ".odp",
    }

    # Plain text files (read directly)
    PLAIN_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}

    # All supported extensions
    SUPPORTED_EXTENSIONS = AZURE_DI_EXTENSIONS | LLAMAPARSE_EXTENSIONS | PLAIN_TEXT_EXTENSIONS

    def __init__(self, llama_api_key: Optional[str] = None, azure_endpoint: Optional[str] = None, azure_api_key: Optional[str] = None):
        """
        Initialize the document parser with both services.
        """
        # Get fresh values from environment
        azure_ep, azure_key = _get_azure_config()

        self.llama_api_key = llama_api_key or _get_llama_key()
        self.azure_endpoint = (azure_endpoint or azure_ep).rstrip('/')
        self.azure_api_key = azure_api_key or azure_key

        if not self.llama_api_key:
            print("[DocumentParser] Warning: No LlamaParse API key configured")
        if not self.azure_endpoint or not self.azure_api_key:
            print("[DocumentParser] Warning: Azure Document Intelligence not configured")
        else:
            print(f"[DocumentParser] Azure DI configured: {self.azure_endpoint}")

    def is_supported(self, file_extension: str) -> bool:
        """Check if a file extension is supported for parsing."""
        ext = file_extension.lower() if file_extension.startswith('.') else f".{file_extension.lower()}"
        return ext in self.SUPPORTED_EXTENSIONS

    def is_plain_text(self, file_extension: str) -> bool:
        """Check if a file is plain text that can be read directly."""
        ext = file_extension.lower() if file_extension.startswith('.') else f".{file_extension.lower()}"
        return ext in self.PLAIN_TEXT_EXTENSIONS

    def _uses_azure_di(self, file_extension: str) -> bool:
        """Check if file should be parsed with Azure Document Intelligence."""
        ext = file_extension.lower() if file_extension.startswith('.') else f".{file_extension.lower()}"
        return ext in self.AZURE_DI_EXTENSIONS

    def _uses_llamaparse(self, file_extension: str) -> bool:
        """Check if file should be parsed with LlamaParse."""
        ext = file_extension.lower() if file_extension.startswith('.') else f".{file_extension.lower()}"
        return ext in self.LLAMAPARSE_EXTENSIONS

    async def parse_bytes(
        self,
        file_bytes: bytes,
        file_name: str,
        file_extension: str
    ) -> str:
        """
        Parse document from bytes, routing to the appropriate service.

        Args:
            file_bytes: Raw file content
            file_name: Original file name
            file_extension: File extension (e.g., ".pdf", "pdf")

        Returns:
            Extracted text content
        """
        ext = file_extension.lower() if file_extension.startswith('.') else f".{file_extension.lower()}"

        # For plain text files, decode directly
        if self.is_plain_text(ext):
            try:
                return file_bytes.decode('utf-8', errors='ignore')
            except Exception as e:
                print(f"[DocumentParser] Error decoding text file: {e}")
                return ""

        # Route to appropriate parser
        if self._uses_azure_di(ext):
            if not self.azure_endpoint or not self.azure_api_key:
                print("[DocumentParser] Azure DI not configured, cannot parse PDF/image")
                return ""
            return await self._parse_with_azure_di(file_bytes, file_name, ext)

        elif self._uses_llamaparse(ext):
            if not self.llama_api_key:
                print("[DocumentParser] LlamaParse not configured, cannot parse Office document")
                return ""
            return await self._parse_with_llamaparse(file_bytes, file_name, ext)

        else:
            print(f"[DocumentParser] Unsupported file type: {ext}")
            return ""

    async def parse_file(self, file_path: str) -> str:
        """
        Parse document from file path.

        Args:
            file_path: Path to the file

        Returns:
            Extracted text content
        """
        path = Path(file_path)
        if not path.exists():
            print(f"[DocumentParser] File not found: {file_path}")
            return ""

        ext = path.suffix.lower()

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        return await self.parse_bytes(file_bytes, path.name, ext)

    async def _parse_with_azure_di(
        self,
        file_bytes: bytes,
        file_name: str,
        extension: str
    ) -> str:
        """
        Parse document using Azure Document Intelligence.

        Args:
            file_bytes: Raw file content
            file_name: Original file name
            extension: File extension with dot

        Returns:
            Extracted text content
        """
        try:
            print(f"[DocumentParser] Parsing {file_name} ({len(file_bytes)} bytes) with Azure Document Intelligence")

            # Use the Layout API for best results
            analyze_url = f"{self.azure_endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze?api-version=2024-11-30"

            headers = {
                "Ocp-Apim-Subscription-Key": self.azure_api_key,
                "Content-Type": self._get_mime_type(extension.lstrip('.'))
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                # Step 1: Submit document for analysis
                response = await client.post(
                    analyze_url,
                    content=file_bytes,
                    headers=headers
                )

                if response.status_code != 202:
                    print(f"[DocumentParser] Azure DI submit failed: {response.status_code} - {response.text}")
                    return ""

                # Get the operation location for polling
                operation_location = response.headers.get("Operation-Location")
                if not operation_location:
                    print("[DocumentParser] No operation location in Azure DI response")
                    return ""

                print(f"[DocumentParser] Azure DI job submitted, polling for result...")

                # Step 2: Poll for completion
                max_attempts = 60  # 5 minutes max
                poll_headers = {
                    "Ocp-Apim-Subscription-Key": self.azure_api_key
                }

                for attempt in range(max_attempts):
                    await asyncio.sleep(2)  # Wait 2 seconds between polls

                    status_response = await client.get(
                        operation_location,
                        headers=poll_headers
                    )

                    if status_response.status_code != 200:
                        print(f"[DocumentParser] Azure DI status check failed: {status_response.status_code}")
                        continue

                    result = status_response.json()
                    status = result.get("status")

                    if status == "succeeded":
                        print(f"[DocumentParser] Azure DI parsing complete for {file_name}")

                        # Extract text from the result
                        analyze_result = result.get("analyzeResult", {})
                        content = analyze_result.get("content", "")

                        if content:
                            print(f"[DocumentParser] Extracted {len(content)} characters from {file_name}")
                            return content

                        # Fallback: concatenate paragraphs
                        paragraphs = analyze_result.get("paragraphs", [])
                        if paragraphs:
                            text = "\n\n".join([p.get("content", "") for p in paragraphs])
                            print(f"[DocumentParser] Extracted {len(text)} characters from paragraphs")
                            return text

                        # Fallback: concatenate pages
                        pages = analyze_result.get("pages", [])
                        text_parts = []
                        for page in pages:
                            for line in page.get("lines", []):
                                text_parts.append(line.get("content", ""))
                        if text_parts:
                            text = "\n".join(text_parts)
                            print(f"[DocumentParser] Extracted {len(text)} characters from lines")
                            return text

                        print("[DocumentParser] Azure DI returned empty content")
                        return ""

                    elif status == "failed":
                        error = result.get("error", {})
                        print(f"[DocumentParser] Azure DI failed: {error.get('message', 'Unknown error')}")
                        return ""

                    elif status in ["notStarted", "running"]:
                        continue
                    else:
                        print(f"[DocumentParser] Unknown Azure DI status: {status}")

                print(f"[DocumentParser] Azure DI timeout waiting for {file_name}")
                return ""

        except Exception as e:
            print(f"[DocumentParser] Error parsing with Azure DI: {e}")
            import traceback
            traceback.print_exc()
            return ""

    async def _parse_with_llamaparse(
        self,
        file_bytes: bytes,
        file_name: str,
        extension: str
    ) -> str:
        """
        Parse document using LlamaParse API.

        Args:
            file_bytes: Raw file content
            file_name: Original file name
            extension: File extension (with or without dot)

        Returns:
            Extracted text content
        """
        try:
            ext = extension.lstrip('.')
            print(f"[DocumentParser] Parsing {file_name} ({len(file_bytes)} bytes) with LlamaParse")

            async with httpx.AsyncClient(timeout=120.0) as client:
                # Create multipart form data
                files = {
                    "file": (file_name, file_bytes, self._get_mime_type(ext))
                }

                headers = {
                    "Authorization": f"Bearer {self.llama_api_key}"
                }

                # Step 1: Upload for parsing
                upload_response = await client.post(
                    f"{LLAMAPARSE_API_URL}/upload",
                    files=files,
                    headers=headers
                )

                if upload_response.status_code != 200:
                    print(f"[DocumentParser] LlamaParse upload failed: {upload_response.status_code} - {upload_response.text}")
                    return ""

                upload_data = upload_response.json()
                job_id = upload_data.get("id")

                if not job_id:
                    print(f"[DocumentParser] No job ID in LlamaParse response: {upload_data}")
                    return ""

                print(f"[DocumentParser] LlamaParse job created: {job_id}")

                # Step 2: Poll for completion
                max_attempts = 60  # 5 minutes max
                for attempt in range(max_attempts):
                    status_response = await client.get(
                        f"{LLAMAPARSE_API_URL}/job/{job_id}",
                        headers=headers
                    )

                    if status_response.status_code != 200:
                        print(f"[DocumentParser] LlamaParse status check failed: {status_response.status_code}")
                        await asyncio.sleep(5)
                        continue

                    status_data = status_response.json()
                    status = status_data.get("status")

                    if status == "SUCCESS":
                        print(f"[DocumentParser] LlamaParse complete for {file_name}")
                        break
                    elif status == "ERROR":
                        print(f"[DocumentParser] LlamaParse error: {status_data.get('error')}")
                        return ""
                    elif status in ["PENDING", "PROCESSING"]:
                        await asyncio.sleep(5)
                    else:
                        print(f"[DocumentParser] Unknown LlamaParse status: {status}")
                        await asyncio.sleep(5)
                else:
                    print(f"[DocumentParser] LlamaParse timeout waiting for {file_name}")
                    return ""

                # Step 3: Get the parsed result
                result_response = await client.get(
                    f"{LLAMAPARSE_API_URL}/job/{job_id}/result/text",
                    headers=headers
                )

                if result_response.status_code != 200:
                    # Try markdown format as fallback
                    result_response = await client.get(
                        f"{LLAMAPARSE_API_URL}/job/{job_id}/result/markdown",
                        headers=headers
                    )

                if result_response.status_code == 200:
                    text = result_response.text
                    print(f"[DocumentParser] Extracted {len(text)} characters from {file_name}")
                    return text
                else:
                    print(f"[DocumentParser] Failed to get LlamaParse result: {result_response.status_code}")
                    return ""

        except Exception as e:
            print(f"[DocumentParser] Error parsing with LlamaParse: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type for file extension."""
        ext = extension.lower().lstrip('.')
        mime_types = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "ppt": "application/vnd.ms-powerpoint",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "txt": "text/plain",
            "md": "text/markdown",
            "csv": "text/csv",
            "json": "application/json",
            "xml": "application/xml",
            "html": "text/html",
            "htm": "text/html",
            "rtf": "application/rtf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "bmp": "image/bmp",
            "tiff": "image/tiff",
            "tif": "image/tiff",
        }
        return mime_types.get(ext, "application/octet-stream")


# Singleton instance for easy access
_parser_instance: Optional[DocumentParser] = None


def get_document_parser(force_new: bool = False) -> DocumentParser:
    """Get the singleton document parser instance."""
    global _parser_instance
    if _parser_instance is None or force_new:
        _parser_instance = DocumentParser()
    return _parser_instance


def reset_parser():
    """Reset the parser singleton to reload configuration."""
    global _parser_instance
    _parser_instance = None


# Convenience function for synchronous code
def parse_document_sync(file_bytes: bytes, file_name: str, extension: str) -> str:
    """
    Synchronous wrapper for parsing documents.

    Args:
        file_bytes: Raw file content
        file_name: Original file name
        extension: File extension

    Returns:
        Extracted text content
    """
    parser = get_document_parser()

    # Run async function in event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new loop in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    parser.parse_bytes(file_bytes, file_name, extension)
                )
                return future.result()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        parser.parse_bytes(file_bytes, file_name, extension)
    )
