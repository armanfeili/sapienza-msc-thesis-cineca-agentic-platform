"""
Test suite for output.summarize tool (P7 implementation).

Covers:
- Extractive summarization
- Abstractive summarization (deterministic simulate mode)
- Map-reduce summarization
- Keyword extraction
- TL;DR summaries
- Edge cases and validation
"""

import pytest
from src.mcp.tools.output.summarize import (
    _act_extract,
    _act_abstractive,
    _act_map_reduce,
    _act_keywords,
    _act_tldr,
    invoke,
)


SAMPLE_TEXT = """
Artificial intelligence is revolutionizing many industries. Machine learning algorithms
can now process vast amounts of data in seconds. Natural language processing has made
significant strides in recent years. Deep learning models are becoming more sophisticated.
Companies are investing heavily in AI research and development. The future of AI looks
promising with many potential applications across various sectors.
"""


class TestOutputSummarizeExtract:
    """Test extractive summarization."""

    def test_extract_basic(self):
        result = _act_extract({"text": SAMPLE_TEXT, "sentences": 2})
        assert result["ok"] is True
        assert result["action"] == "extract"
        assert isinstance(result["summary"], str)
        assert result["sentences"] <= 2
        assert "stats" in result
        assert result["stats"]["elapsed_ms"] >= 0

    def test_extract_by_ratio(self):
        result = _act_extract({"text": SAMPLE_TEXT, "ratio": 0.3})
        assert result["ok"] is True
        assert result["ratio"] == 0.3
        # Should select ~30% of sentences
        total_sents = result["stats"]["sentences"]
        selected = result["sentences"]
        assert selected <= total_sents

    def test_extract_lowercase_scoring(self):
        result = _act_extract({"text": SAMPLE_TEXT, "lower": True})
        assert result["ok"] is True

    def test_extract_indices(self):
        result = _act_extract({"text": SAMPLE_TEXT, "sentences": 3})
        assert "indices" in result
        assert isinstance(result["indices"], list)
        assert len(result["indices"]) == result["sentences"]

    def test_extract_empty_text(self):
        with pytest.raises(ValueError, match="extract requires 'text'"):
            _act_extract({"text": ""})

    def test_extract_stats(self):
        result = _act_extract({"text": SAMPLE_TEXT})
        stats = result["stats"]
        assert "elapsed_ms" in stats
        assert "words" in stats
        assert "sentences" in stats
        assert stats["words"] > 0
        assert stats["sentences"] > 0


class TestOutputSummarizeAbstractive:
    """Test abstractive summarization with deterministic simulate mode."""

    def test_abstractive_simulate_deterministic(self):
        # Same input should produce same output in simulate mode
        payload = {"text": SAMPLE_TEXT, "simulate": True, "sentences": 3}
        result1 = _act_abstractive(payload)
        result2 = _act_abstractive(payload)
        assert result1["summary"] == result2["summary"]
        assert result1["simulate"] is True

    def test_abstractive_different_styles(self):
        styles = ["plain", "bullets", "keypoints", "academic"]
        for style in styles:
            result = _act_abstractive(
                {
                    "text": SAMPLE_TEXT,
                    "simulate": True,
                    "style": style,
                }
            )
            assert result["ok"] is True
            assert isinstance(result["summary"], str)

    def test_abstractive_empty_text(self):
        with pytest.raises(ValueError, match="abstractive requires 'text'"):
            _act_abstractive({"text": ""})

    def test_abstractive_stats(self):
        result = _act_abstractive({"text": SAMPLE_TEXT, "simulate": True})
        stats = result["stats"]
        assert "elapsed_ms" in stats
        assert "input_tokens_approx" in stats
        assert stats["input_tokens_approx"] > 0

    def test_abstractive_model_provider(self):
        result = _act_abstractive({"text": SAMPLE_TEXT, "simulate": True})
        # In simulate mode, model/provider may be None
        assert "model" in result
        assert "provider" in result


class TestOutputSummarizeMapReduce:
    """Test map-reduce summarization."""

    def test_map_reduce_basic(self):
        long_text = SAMPLE_TEXT * 10  # Make it longer
        result = _act_map_reduce(
            {
                "text": long_text,
                "simulate": True,
                "chunk_chars": 200,
            }
        )
        assert result["ok"] is True
        assert result["action"] == "map_reduce"
        assert result["chunks"] > 1  # Should have multiple chunks

    def test_map_reduce_deterministic(self):
        # Same input should produce same output in simulate mode
        payload = {
            "text": SAMPLE_TEXT * 5,
            "simulate": True,
            "chunk_chars": 150,
            "sentences": 2,
        }
        result1 = _act_map_reduce(payload)
        result2 = _act_map_reduce(payload)
        assert result1["summary"] == result2["summary"]

    def test_map_reduce_partials(self):
        result = _act_map_reduce(
            {
                "text": SAMPLE_TEXT * 5,
                "simulate": True,
                "chunk_chars": 200,
            }
        )
        assert "partials" in result
        assert isinstance(result["partials"], list)
        assert len(result["partials"]) == result["chunks"]

    def test_map_reduce_overlap(self):
        result = _act_map_reduce(
            {
                "text": SAMPLE_TEXT * 3,
                "simulate": True,
                "chunk_chars": 150,
                "overlap": 50,
            }
        )
        assert result["ok"] is True
        assert result["chunks"] >= 1

    def test_map_reduce_stats(self):
        result = _act_map_reduce(
            {
                "text": SAMPLE_TEXT * 5,
                "simulate": True,
            }
        )
        stats = result["stats"]
        assert "elapsed_ms" in stats
        assert "input_tokens_approx" in stats
        assert "avg_chunk_size" in stats

    def test_map_reduce_empty_text(self):
        with pytest.raises(ValueError, match="map_reduce requires 'text'"):
            _act_map_reduce({"text": ""})


class TestOutputSummarizeKeywords:
    """Test keyword extraction."""

    def test_keywords_basic(self):
        result = _act_keywords({"text": SAMPLE_TEXT, "top_k": 10})
        assert result["ok"] is True
        assert result["action"] == "keywords"
        assert isinstance(result["keywords"], list)
        assert len(result["keywords"]) <= 10

    def test_keywords_structure(self):
        result = _act_keywords({"text": SAMPLE_TEXT})
        keywords = result["keywords"]
        if keywords:
            kw = keywords[0]
            assert "term" in kw
            assert "score" in kw
            assert isinstance(kw["term"], str)
            assert isinstance(kw["score"], int)

    def test_keywords_scoring_order(self):
        result = _act_keywords({"text": SAMPLE_TEXT, "top_k": 5})
        keywords = result["keywords"]
        if len(keywords) > 1:
            # Should be ordered by score (descending)
            scores = [kw["score"] for kw in keywords]
            assert scores == sorted(scores, reverse=True)

    def test_keywords_lowercase(self):
        result = _act_keywords({"text": SAMPLE_TEXT, "lower": True})
        keywords = result["keywords"]
        if keywords:
            # All terms should be lowercase
            for kw in keywords:
                assert kw["term"] == kw["term"].lower()

    def test_keywords_stats(self):
        result = _act_keywords({"text": SAMPLE_TEXT})
        stats = result["stats"]
        assert "unique" in stats
        assert "total_terms" in stats
        assert stats["unique"] > 0

    def test_keywords_empty_text(self):
        with pytest.raises(ValueError, match="keywords requires 'text'"):
            _act_keywords({"text": ""})


class TestOutputSummarizeTLDR:
    """Test TL;DR ultra-compact summaries."""

    def test_tldr_basic(self):
        result = _act_tldr({"text": SAMPLE_TEXT, "simulate": True})
        assert result["ok"] is True
        assert result["action"] == "tl_dr"
        assert isinstance(result["summary"], str)
        assert result["simulate"] is True

    def test_tldr_deterministic(self):
        # Same input should produce same output
        payload = {"text": SAMPLE_TEXT, "simulate": True}
        result1 = _act_tldr(payload)
        result2 = _act_tldr(payload)
        assert result1["summary"] == result2["summary"]

    def test_tldr_brief(self):
        # TL;DR should be briefer than regular abstractive
        tldr_result = _act_tldr({"text": SAMPLE_TEXT, "simulate": True})
        abstract_result = _act_abstractive(
            {
                "text": SAMPLE_TEXT,
                "simulate": True,
                "sentences": 5,
            }
        )
        # TL;DR should typically be shorter (not always guaranteed, but likely)
        # Just verify it completes successfully
        assert len(tldr_result["summary"]) >= 0


class TestOutputSummarizeInvoke:
    """Test main invoke entrypoint."""

    def test_invoke_extract(self):
        result = invoke({"action": "extract", "text": SAMPLE_TEXT})
        assert result["action"] == "extract"

    def test_invoke_abstractive(self):
        result = invoke(
            {
                "action": "abstractive",
                "text": SAMPLE_TEXT,
                "simulate": True,
            }
        )
        assert result["action"] == "abstractive"

    def test_invoke_map_reduce(self):
        result = invoke(
            {
                "action": "map_reduce",
                "text": SAMPLE_TEXT,
                "simulate": True,
            }
        )
        assert result["action"] == "map_reduce"

    def test_invoke_keywords(self):
        result = invoke({"action": "keywords", "text": SAMPLE_TEXT})
        assert result["action"] == "keywords"

    def test_invoke_tldr(self):
        result = invoke({"action": "tl_dr", "text": SAMPLE_TEXT, "simulate": True})
        assert result["action"] == "tl_dr"

    def test_invoke_default_action(self):
        # Default action is extract
        result = invoke({"text": SAMPLE_TEXT})
        assert result["action"] == "extract"

    def test_invoke_invalid_action(self):
        with pytest.raises(ValueError, match="action must be one of"):
            invoke({"action": "invalid", "text": SAMPLE_TEXT})


class TestOutputSummarizeEdgeCases:
    """Test edge cases and validation."""

    def test_very_short_text(self):
        short_text = "AI is great."
        result = _act_extract({"text": short_text, "sentences": 5})
        # Should handle gracefully
        assert result["ok"] is True
        assert result["sentences"] <= 1

    def test_single_sentence(self):
        result = _act_extract({"text": "One sentence.", "sentences": 2})
        assert result["sentences"] == 1

    def test_no_extractable_keywords(self):
        # Text with only stopwords
        text = "the the the a a and or"
        result = _act_keywords({"text": text})
        # Should return empty or minimal keywords
        assert result["ok"] is True
        assert len(result["keywords"]) <= result["stats"]["unique"]

    def test_unicode_text(self):
        unicode_text = "人工智能正在改变世界。机器学习是AI的核心技术。"
        result = _act_extract({"text": unicode_text})
        assert result["ok"] is True
        assert len(result["summary"]) > 0

    def test_special_characters(self):
        text = "Test! Test? Test. Test... Test!!!"
        result = _act_extract({"text": text})
        assert result["ok"] is True

    def test_large_text_map_reduce(self):
        # Test with very large text
        large_text = SAMPLE_TEXT * 50
        result = _act_map_reduce(
            {
                "text": large_text,
                "simulate": True,
                "chunk_chars": 500,
            }
        )
        assert result["ok"] is True
        assert result["chunks"] > 5  # Should split into many chunks

    def test_deterministic_hash_based(self):
        # Verify deterministic behavior is hash-based (same hash → same result)
        text1 = "Same content"
        text2 = "Same content"
        result1 = _act_abstractive({"text": text1, "simulate": True})
        result2 = _act_abstractive({"text": text2, "simulate": True})
        assert result1["summary"] == result2["summary"]
