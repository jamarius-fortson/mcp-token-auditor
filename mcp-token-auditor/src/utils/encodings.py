"""Encoding and tokenization utilities."""

import json
import tiktoken
from typing import Any, Dict
import logging
import hashlib

logger = logging.getLogger(__name__)


class TokenCounter:
    """Deterministic token counting using tiktoken."""

    def __init__(self, encoding_name: str = "o200k_base"):
        """Initialize with a specific tiktoken encoding.
        
        Args:
            encoding_name: tiktoken encoding name (o200k_base, cl100k_base, etc.)
            
        Raises:
            ValueError: If encoding cannot be loaded
        """
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
            self.encoding_name = encoding_name
            self._cache: Dict[str, int] = {}
            logger.info(f"Initialized TokenCounter with encoding: {encoding_name}")
        except Exception as e:
            logger.error(f"Failed to load encoding {encoding_name}: {e}")
            raise ValueError(f"Invalid encoding name: {encoding_name}") from e

    def count(self, text: str) -> int:
        """Count tokens in text deterministically.
        
        Args:
            text: String to tokenize
            
        Returns:
            Token count
            
        Raises:
            ValueError: If text is None or tokenization fails
        """
        if text is None:
            raise ValueError("Text cannot be None")
        
        if not isinstance(text, str):
            raise ValueError(f"Text must be string, got {type(text)}")
        
        try:
            # Deterministic cache lookup
            cache_key = hashlib.md5(text.encode('utf-8')).hexdigest()
            if cache_key in self._cache:
                return self._cache[cache_key]

            tokens = self.encoding.encode(text)
            count = len(tokens)
            
            # Simple LRU-style limit (1000 items)
            if len(self._cache) < 1000:
                self._cache[cache_key] = count
                
            return count
        except Exception as e:
            logger.error(f"Token counting failed for text (length {len(text)}): {e}")
            raise ValueError(f"Token counting failed: {str(e)}") from e

    def count_tool_name(self, name: str) -> int:
        """Count tokens in tool name.
        
        Args:
            name: Tool name string
            
        Returns:
            Token count
            
        Raises:
            ValueError: If name is invalid
        """
        if not name or not isinstance(name, str):
            raise ValueError("Tool name must be a non-empty string")
        return self.count(name)

    def count_description(self, description: str) -> int:
        """Count tokens in tool description.
        
        Args:
            description: Tool description string
            
        Returns:
            Token count
            
        Raises:
            ValueError: If description is invalid
        """
        if description is None:
            description = ""  # Allow empty descriptions
        if not isinstance(description, str):
            raise ValueError(f"Description must be string, got {type(description)}")
        return self.count(description)

    def count_schema(self, schema: Dict[str, Any]) -> int:
        """Count tokens in JSON schema (serialized canonically).
        
        Args:
            schema: JSON schema object
            
        Returns:
            Token count of canonical JSON representation
            
        Raises:
            ValueError: If schema is invalid
        """
        if schema is None:
            raise ValueError("Schema cannot be None")
        
        if not isinstance(schema, dict):
            raise ValueError(f"Schema must be dict, got {type(schema)}")
        
        try:
            # Canonical serialization: sorted keys, no whitespace
            canonical = json.dumps(schema, sort_keys=True, separators=(',', ':'))
            return self.count(canonical)
        except (TypeError, ValueError) as e:
            logger.error(f"Schema serialization failed: {e}")
            raise ValueError(f"Invalid schema format: {str(e)}") from e

    def count_tool_metadata(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any]
    ) -> Dict[str, int]:
        """Count tokens for all components of tool metadata.
        
        Args:
            name: Tool name
            description: Tool description
            schema: Input schema
            
        Returns:
            Dict with name_tokens, description_tokens, schema_tokens, total_tool_tokens
            
        Raises:
            ValueError: If any component is invalid
        """
        try:
            name_tokens = self.count_tool_name(name)
            desc_tokens = self.count_description(description)
            schema_tokens = self.count_schema(schema)
            total = name_tokens + desc_tokens + schema_tokens

            return {
                "name_tokens": name_tokens,
                "description_tokens": desc_tokens,
                "schema_tokens": schema_tokens,
                "total_tool_tokens": total,
            }
        except ValueError as e:
            logger.error(f"Tool metadata counting failed: {e}")
            raise
