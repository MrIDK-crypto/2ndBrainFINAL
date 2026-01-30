"""
Code Analysis Service
LLM-based code analysis to extract knowledge from GitHub repositories.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime, timezone
from openai import AzureOpenAI

from config.config import (
    AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT,
    AZURE_CHAT_DEPLOYMENT, AZURE_API_VERSION
)


class CodeAnalysisService:
    """
    Analyze code repositories using LLM to extract knowledge.

    Multi-stage analysis:
    1. Repository Overview - High-level architecture
    2. File-by-File Analysis - Detailed component analysis
    3. Knowledge Synthesis - Combined insights
    """

    def __init__(self):
        """Initialize Azure OpenAI client"""
        self.client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )

    # =========================================================================
    # STAGE 1: REPOSITORY OVERVIEW
    # =========================================================================

    def analyze_repository_structure(
        self,
        repo_name: str,
        repo_description: Optional[str],
        file_list: List[Dict]
    ) -> Dict:
        """
        Analyze repository structure to understand high-level architecture.

        Args:
            repo_name: Repository name
            repo_description: Repository description
            file_list: List of files with path, language, size

        Returns:
            {
                'architecture': 'Description of overall architecture',
                'tech_stack': ['Python', 'Flask', 'React'],
                'patterns': ['MVC', 'REST API', 'OAuth'],
                'components': {
                    'Backend': ['api/', 'services/'],
                    'Frontend': ['components/', 'pages/']
                },
                'purpose': 'What this codebase does'
            }
        """
        # Build file tree summary
        file_tree_lines = []
        for file in file_list[:200]:  # Limit to first 200 files
            file_tree_lines.append(f"  {file['path']} ({file['language']}, {file['lines']} lines)")

        file_tree_text = "\n".join(file_tree_lines)

        prompt = f"""You are a senior software architect analyzing a codebase.

Repository: {repo_name}
Description: {repo_description or 'N/A'}

File Tree:
{file_tree_text}

Analyze this repository structure and provide:

1. **Architecture Overview** (2-3 sentences):
   - What type of application is this? (web app, API, CLI tool, library, etc.)
   - What is the overall architecture pattern? (MVC, microservices, monolith, etc.)

2. **Tech Stack** (list of technologies):
   - Programming languages
   - Frameworks
   - Key libraries
   - Infrastructure tools

3. **Design Patterns** (list patterns you detect):
   - Architectural patterns
   - Code organization patterns
   - Integration patterns

4. **Component Breakdown** (map of component categories to directories):
   - Group related directories into logical components
   - E.g., {{"Backend API": ["api/", "services/"], "Frontend": ["components/"]}}

5. **Purpose** (1-2 sentences):
   - What business problem does this solve?
   - Who is the target user?

Return ONLY a valid JSON object with these 5 keys: architecture, tech_stack, patterns, components, purpose.
No markdown, no explanation, just the JSON object."""

        try:
            response = self.client.chat.completions.create(
                model=AZURE_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": "You are a senior software architect. You analyze code and return structured insights in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()

            # Try to parse JSON
            # Remove markdown code blocks if present
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)

            print(f"[CodeAnalysis] Repository structure analyzed: {len(result.get('tech_stack', []))} technologies, {len(result.get('patterns', []))} patterns")

            return result

        except Exception as e:
            print(f"[CodeAnalysis] Error analyzing repository structure: {e}")
            return {
                'architecture': 'Unable to analyze',
                'tech_stack': [],
                'patterns': [],
                'components': {},
                'purpose': 'Analysis failed'
            }

    # =========================================================================
    # STAGE 2: FILE-BY-FILE ANALYSIS
    # =========================================================================

    def analyze_code_file(
        self,
        file_path: str,
        file_content: str,
        file_language: str,
        repo_context: Dict
    ) -> Dict:
        """
        Analyze a single code file to extract knowledge.

        Args:
            file_path: Path to file
            file_content: File content
            file_language: Programming language
            repo_context: Repository overview from stage 1

        Returns:
            {
                'summary': 'What this file does',
                'key_functions': ['function1', 'function2'],
                'dependencies': ['import1', 'import2'],
                'business_logic': 'Core business logic description',
                'api_endpoints': ['GET /users', 'POST /login'],  # if applicable
                'data_models': ['User', 'Session'],  # if applicable
                'configuration': {'key': 'value'},  # if config file
                'important_notes': ['Security consideration', 'Performance tip']
            }
        """
        # Truncate very long files
        max_chars = 30000
        if len(file_content) > max_chars:
            file_content = file_content[:max_chars] + "\n\n[... truncated ...]"

        prompt = f"""You are analyzing a code file from a {repo_context.get('architecture', 'software')} project.

Repository Context:
- Purpose: {repo_context.get('purpose', 'N/A')}
- Tech Stack: {', '.join(repo_context.get('tech_stack', [])[:5])}
- Architecture: {repo_context.get('architecture', 'N/A')}

File: {file_path}
Language: {file_language}

Code:
```{file_language.lower()}
{file_content}
```

Analyze this file and extract:

1. **Summary** (1-2 sentences): What does this file do?

2. **Key Functions/Classes** (list of names): Main functions, classes, or components defined

3. **Dependencies** (list): External libraries/modules imported

4. **Business Logic** (1-2 sentences): Core business logic or algorithms (if any)

5. **API Endpoints** (list, if applicable): HTTP endpoints defined (e.g., "GET /users", "POST /login")

6. **Data Models** (list, if applicable): Database models or data structures defined

7. **Configuration** (dict, if applicable): Configuration settings or environment variables

8. **Important Notes** (list): Security considerations, performance notes, edge cases, TODOs

Return ONLY a valid JSON object with these 8 keys. Use empty array/dict for N/A fields.
No markdown, no explanation, just the JSON object."""

        try:
            response = self.client.chat.completions.create(
                model=AZURE_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": "You are a senior software engineer. You analyze code and extract structured insights in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500
            )

            content = response.choices[0].message.content.strip()

            # Remove markdown if present
            if content.startswith('```'):
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)

            return result

        except Exception as e:
            print(f"[CodeAnalysis] Error analyzing {file_path}: {e}")
            return {
                'summary': 'Analysis failed',
                'key_functions': [],
                'dependencies': [],
                'business_logic': '',
                'api_endpoints': [],
                'data_models': [],
                'configuration': {},
                'important_notes': []
            }

    # =========================================================================
    # STAGE 3: KNOWLEDGE SYNTHESIS
    # =========================================================================

    def synthesize_repository_knowledge(
        self,
        repo_name: str,
        repo_overview: Dict,
        file_analyses: List[Dict]
    ) -> str:
        """
        Synthesize all analyses into comprehensive documentation.

        Args:
            repo_name: Repository name
            repo_overview: Repository structure analysis
            file_analyses: List of file analysis results

        Returns:
            Comprehensive documentation as markdown text
        """
        # Build file summaries
        file_summaries = []
        for analysis in file_analyses[:50]:  # Limit to 50 most important files
            file_summaries.append(
                f"- **{analysis['file_path']}**: {analysis['summary']}"
            )

        # Collect all API endpoints
        all_endpoints = []
        for analysis in file_analyses:
            all_endpoints.extend(analysis.get('api_endpoints', []))

        # Collect all data models
        all_models = []
        for analysis in file_analyses:
            all_models.extend(analysis.get('data_models', []))

        # Collect important notes
        all_notes = []
        for analysis in file_analyses:
            notes = analysis.get('important_notes', [])
            if notes:
                all_notes.append(f"**{analysis['file_path']}**: {', '.join(notes)}")

        prompt = f"""You are a technical writer creating comprehensive documentation for a codebase.

Repository: {repo_name}

Overview:
- Purpose: {repo_overview.get('purpose', 'N/A')}
- Architecture: {repo_overview.get('architecture', 'N/A')}
- Tech Stack: {', '.join(repo_overview.get('tech_stack', []))}
- Patterns: {', '.join(repo_overview.get('patterns', []))}

Components:
{json.dumps(repo_overview.get('components', {}), indent=2)}

File Summaries:
{chr(10).join(file_summaries[:30])}

API Endpoints:
{chr(10).join(f'- {ep}' for ep in set(all_endpoints[:20]))}

Data Models:
{chr(10).join(f'- {model}' for model in set(all_models[:20]))}

Important Notes:
{chr(10).join(all_notes[:10])}

Create comprehensive documentation in markdown format with these sections:

# {repo_name} - Technical Documentation

## Overview
[2-3 paragraphs describing what this codebase does, who it's for, and why it exists]

## Architecture
[Describe the system architecture, major components, and how they interact]

## Technology Stack
[List and briefly explain the key technologies used]

## Core Components
[Describe the main components/modules and their responsibilities]

## API Reference
[List and describe the main API endpoints, if applicable]

## Data Models
[Describe key data models and their relationships, if applicable]

## Key Features
[List and explain the main features/capabilities]

## Development Patterns
[Describe coding patterns, conventions, and best practices used]

## Important Notes
[Security considerations, performance tips, known limitations, future improvements]

Write clear, concise documentation that would help a new developer understand this codebase."""

        try:
            response = self.client.chat.completions.create(
                model=AZURE_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": "You are a technical writer. You create clear, comprehensive documentation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=4000
            )

            documentation = response.choices[0].message.content.strip()

            print(f"[CodeAnalysis] Generated {len(documentation)} characters of documentation")

            return documentation

        except Exception as e:
            print(f"[CodeAnalysis] Error synthesizing knowledge: {e}")
            return f"# {repo_name}\n\nError generating documentation: {str(e)}"

    # =========================================================================
    # MAIN ANALYSIS PIPELINE
    # =========================================================================

    def analyze_repository(
        self,
        repo_name: str,
        repo_description: Optional[str],
        code_files: List[Dict],
        max_files_to_analyze: int = 30
    ) -> Dict:
        """
        Complete repository analysis pipeline.

        Args:
            repo_name: Repository name
            repo_description: Repository description
            code_files: List of code files from GitHubConnector.fetch_repository_code()
            max_files_to_analyze: Maximum files to analyze in detail

        Returns:
            {
                'repository_overview': {...},
                'file_analyses': [{...}, {...}],
                'documentation': 'Markdown documentation',
                'analyzed_at': '2024-12-09T...',
                'stats': {
                    'total_files': 100,
                    'analyzed_files': 30,
                    'total_lines': 5000,
                    'languages': {'Python': 60, 'JavaScript': 30}
                }
            }
        """
        print(f"[CodeAnalysis] Starting repository analysis: {repo_name}")
        print(f"[CodeAnalysis] Total files: {len(code_files)}")

        # Stage 1: Analyze repository structure
        print(f"[CodeAnalysis] Stage 1: Analyzing repository structure...")
        repo_overview = self.analyze_repository_structure(
            repo_name=repo_name,
            repo_description=repo_description,
            file_list=code_files
        )

        # Stage 2: Analyze individual files
        print(f"[CodeAnalysis] Stage 2: Analyzing individual files (max {max_files_to_analyze})...")

        # Prioritize important files (README, config, main code files)
        priority_files = sorted(
            code_files,
            key=lambda f: (
                1000 if 'readme' in f['path'].lower() else 0,
                100 if f['path'].endswith('.md') else 0,
                50 if 'config' in f['path'].lower() or 'settings' in f['path'].lower() else 0,
                10 if f['language'] in ['Python', 'JavaScript', 'TypeScript', 'Go', 'Java'] else 0,
                -f['lines']  # Prefer longer files
            ),
            reverse=True
        )

        file_analyses = []
        for i, file_data in enumerate(priority_files[:max_files_to_analyze], 1):
            print(f"[CodeAnalysis]   [{i}/{min(max_files_to_analyze, len(priority_files))}] Analyzing: {file_data['path']}")

            analysis = self.analyze_code_file(
                file_path=file_data['path'],
                file_content=file_data['content'],
                file_language=file_data['language'],
                repo_context=repo_overview
            )

            # Add file metadata
            analysis['file_path'] = file_data['path']
            analysis['language'] = file_data['language']
            analysis['lines'] = file_data['lines']

            file_analyses.append(analysis)

        # Stage 3: Synthesize knowledge
        print(f"[CodeAnalysis] Stage 3: Synthesizing repository knowledge...")
        documentation = self.synthesize_repository_knowledge(
            repo_name=repo_name,
            repo_overview=repo_overview,
            file_analyses=file_analyses
        )

        # Calculate statistics
        language_counts = {}
        total_lines = 0
        for file in code_files:
            lang = file['language']
            language_counts[lang] = language_counts.get(lang, 0) + 1
            total_lines += file['lines']

        result = {
            'repository_overview': repo_overview,
            'file_analyses': file_analyses,
            'documentation': documentation,
            'analyzed_at': datetime.now(timezone.utc).isoformat(),
            'stats': {
                'total_files': len(code_files),
                'analyzed_files': len(file_analyses),
                'total_lines': total_lines,
                'languages': language_counts
            }
        }

        print(f"[CodeAnalysis] Analysis complete!")
        print(f"[CodeAnalysis]   - Total files: {len(code_files)}")
        print(f"[CodeAnalysis]   - Analyzed files: {len(file_analyses)}")
        print(f"[CodeAnalysis]   - Documentation: {len(documentation)} chars")

        return result
