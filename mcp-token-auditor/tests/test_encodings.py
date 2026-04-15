# Tests for token counting

import pytest
from src.utils.encodings import TokenCounter


def test_token_counter_init():
    """Test TokenCounter initialization."""
    counter = TokenCounter(encoding_name="o200k_base")
    assert counter.encoding_name == "o200k_base"


def test_count_tool_name(token_counter):
    """Test counting tokens in tool name."""
    count = token_counter.count_tool_name("list_files")
    assert count > 0
    assert isinstance(count, int)


def test_count_description(token_counter):
    """Test counting tokens in description."""
    desc = "This is a sample tool description"
    count = token_counter.count_description(desc)
    assert count > 0
    assert isinstance(count, int)


def test_count_tool_metadata(token_counter, sample_tool_metadata):
    """Test counting tokens for complete tool metadata."""
    result = token_counter.count_tool_metadata(
        name=sample_tool_metadata["name"],
        description=sample_tool_metadata["description"],
        schema=sample_tool_metadata["input_schema"],
    )
    
    assert "name_tokens" in result
    assert "description_tokens" in result
    assert "schema_tokens" in result
    assert "total_tool_tokens" in result
    
    # Total should be sum of parts
    assert result["total_tool_tokens"] == (
        result["name_tokens"] +
        result["description_tokens"] +
        result["schema_tokens"]
    )


def test_deterministic_counting(token_counter):
    """Test that token counting is deterministic."""
    text = "This is a test string for deterministic counting"
    count1 = token_counter.count(text)
    count2 = token_counter.count(text)
    assert count1 == count2


def test_empty_string(token_counter):
    """Test counting empty string."""
    assert token_counter.count("") == 0
    assert token_counter.count_tool_name("") == 0
    assert token_counter.count_description("") == 0
    assert token_counter.count_schema({}) == 0
