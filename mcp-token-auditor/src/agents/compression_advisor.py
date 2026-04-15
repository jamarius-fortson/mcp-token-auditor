"""Compression Advisor Agent - Static analysis for tool description optimization."""

import logging
import re
from typing import Dict, List, Any, Optional

from src.models.audit import CompressionSuggestion
from src.utils.encodings import TokenCounter
from src.storage.database import AuditDatabase

logger = logging.getLogger(__name__)

# Heuristic weights
REDUNDANCY_PHRASES = r"(tool|function|method|call|execute|run|perform)"
VERBOSE_THRESHOLD = 0.05  # tokens per character


class CompressionAdvisorAgent:
    """Static analysis engine for tool description optimization."""

    def __init__(self, token_counter: TokenCounter, db: AuditDatabase, min_confidence: float = 0.65):
        """Initialize compression advisor.
        
        Args:
            token_counter: TokenCounter instance
            db: AuditDatabase instance
            min_confidence: Minimum confidence score to emit suggestion
        """
        self.token_counter = token_counter
        self.db = db
        self.min_confidence = min_confidence
        logger.info(f"CompressionAdvisorAgent initialized (min_confidence: {min_confidence})")

    async def analyze_tool(
        self,
        server_id: str,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
    ) -> Optional[List[CompressionSuggestion]]:
        """Analyze tool for compression opportunities.
        
        Args:
            server_id: Server ID
            tool_name: Tool name
            description: Tool description
            input_schema: Input schema
            
        Returns:
            List of compression suggestions (filtered by confidence)
        """
        suggestions: List[CompressionSuggestion] = []
        current_tokens = self.token_counter.count_description(description)
        
        # 1. Redundancy Detection
        if self._has_redundancy(tool_name, description):
            suggested = self._remove_redundancy(description)
            tokens_saved = current_tokens - self.token_counter.count_description(suggested)
            if tokens_saved > 0:
                confidence = 0.75  # High confidence for redundancy removal
                if confidence >= self.min_confidence:
                    suggestions.append(CompressionSuggestion(
                        tool_name=tool_name,
                        server_id=server_id,
                        heuristic="redundancy",
                        original_text=description,
                        suggested_text=suggested,
                        current_tokens=current_tokens,
                        token_delta=-tokens_saved,
                        confidence=confidence,
                    ))
        
        # 2. Verbosity Scoring
        verbosity_score = self._calculate_verbosity(description)
        if verbosity_score > 0.08:  # High verbosity threshold
            suggested = self._compress_verbosity(description)
            suggested_tokens = self.token_counter.count_description(suggested)
            tokens_saved = current_tokens - suggested_tokens
            
            if tokens_saved > 0 and suggested_tokens >= 8:  # Don't compress below 8 tokens
                confidence = 0.70
                if confidence >= self.min_confidence:
                    suggestions.append(CompressionSuggestion(
                        tool_name=tool_name,
                        server_id=server_id,
                        heuristic="verbosity",
                        original_text=description,
                        suggested_text=suggested,
                        current_tokens=current_tokens,
                        token_delta=-tokens_saved,
                        confidence=confidence,
                    ))
        
        # 3. Schema Bloat Detection
        schema_description = input_schema.get("description", "")
        if schema_description and len(schema_description) > 100:
            schema_tokens = self.token_counter.count_description(schema_description)
            if schema_tokens > 20:
                suggested_schema_desc = schema_description[:80]
                suggested_tokens = self.token_counter.count_description(suggested_schema_desc)
                tokens_saved = schema_tokens - suggested_tokens
                
                if tokens_saved > 0:
                    confidence = 0.60  # Lower confidence for schema changes
                    if confidence >= self.min_confidence:
                        suggestions.append(CompressionSuggestion(
                            tool_name=tool_name,
                            server_id=server_id,
                            heuristic="schema_bloat",
                            original_text=f"schema.description: {schema_description}",
                            suggested_text=f"schema.description: {suggested_schema_desc}",
                            current_tokens=schema_tokens,
                            token_delta=-tokens_saved,
                            confidence=confidence,
                        ))
        
        # 4. Cloudflare Code Mode Pattern
        if len(description) > 200:
            code_mode = self._suggest_code_mode(tool_name, description)
            code_tokens = self.token_counter.count_description(code_mode)
            tokens_saved = current_tokens - code_tokens
            
            if tokens_saved > 20:  # Meaningful savings
                confidence = 0.65
                if confidence >= self.min_confidence:
                    suggestions.append(CompressionSuggestion(
                        tool_name=tool_name,
                        server_id=server_id,
                        heuristic="cloudflare_code_mode",
                        original_text=description,
                        suggested_text=code_mode,
                        current_tokens=current_tokens,
                        token_delta=-tokens_saved,
                        confidence=confidence,
                    ))
        
        # 5. Deduplication Hints
        similar_tools = self.db.get_similar_tools(description)
        if len(similar_tools) > 1:  # More than just this tool
            others = [f"{t['server_id']}:{t['tool_name']}" for t in similar_tools if t['tool_name'] != tool_name]
            if others:
                confidence = 0.70
                if confidence >= self.min_confidence:
                    # Explicitly join first two items to avoid slice issues in some checkers
                    limit = 2
                    other_names = []
                    count = 0
                    for name in others:
                        if count < limit:
                            other_names.append(name)
                            count += 1
                        else:
                            break
                    
                    suggestions.append(CompressionSuggestion(
                        tool_name=tool_name,
                        server_id=server_id,
                        heuristic="deduplication",
                        original_text=description,
                        suggested_text=f"CONSIDER SHARED SCHEMA: Overlaps with {', '.join(other_names)}",
                        current_tokens=current_tokens,
                        token_delta=0,  # Strategy only
                        confidence=confidence,
                    ))
        
        logger.info(f"Analyzed {tool_name}: {len(suggestions)} suggestions generated")
        return suggestions if suggestions else None

    def _has_redundancy(self, tool_name: str, description: str) -> bool:
        """Check if description contains redundancy with tool name."""
        name_lower = tool_name.lower()
        desc_lower = description.lower()
        
        # Check if tool name or variations appear in description
        variations = [name_lower, f"this {name_lower}", f"the {name_lower}"]
        return any(var in desc_lower for var in variations)

    def _remove_redundancy(self, description: str) -> str:
        """Remove redundant references from description."""
        # Simple regex removal of common redundancy patterns
        result = re.sub(r"this tool|this function|this method", "", description, flags=re.IGNORECASE)
        result = re.sub(r"\s+", " ", result).strip()
        return result

    def _calculate_verbosity(self, description: str) -> float:
        """Calculate verbosity score (tokens per character)."""
        if not description:
            return 0.0
        tokens = self.token_counter.count_description(description)
        return tokens / len(description)

    def _compress_verbosity(self, description: str) -> str:
        """Compress verbose description."""
        # Remove unnecessary articles and conjunctions
        result = re.sub(r"\b(a|an|the|and|or|which|that)\b\s+", "", description, flags=re.IGNORECASE)
        result = re.sub(r"\s+", " ", result).strip()
        
        # Avoid slicing directly if lint is being tricky
        max_len = int(len(description) * 0.7)
        return result[:max_len]

    def _suggest_code_mode(self, tool_name: str, description: str) -> str:
        """Suggest Cloudflare code mode format."""
        # Extract key information
        action = "Execute"
        if "list" in description.lower():
            action = "LIST"
        elif "create" in description.lower():
            action = "CREATE"
        elif "delete" in description.lower():
            action = "DELETE"
        
        input_type = "object"
        output_type = "result"
        
        code_mode = f"ACTION: {action}. INPUT: {input_type}. OUTPUT: {output_type}."
        return code_mode
