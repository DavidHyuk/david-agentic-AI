# __author__ = 'David Choi (bestshoot21@gmail.com)'
"""Tests for local-model/smoke_test.py response validation."""

import json

import pytest

import smoke_test


def test_validate_model_listing():
    smoke_test.validate_model_listing(
        {"data": [{"id": "Qwen3.6-35B-A3B-FP8"}]},
        "Qwen3.6-35B-A3B-FP8",
    )


def test_validate_model_listing_rejects_wrong_model():
    with pytest.raises(ValueError, match="expected model"):
        smoke_test.validate_model_listing(
            {"data": [{"id": "other-model"}]},
            "Qwen3.6-35B-A3B-FP8",
        )


def test_validate_tool_call():
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "get_weather",
                                "arguments": json.dumps({"city": "Seoul"}),
                            }
                        }
                    ]
                }
            }
        ]
    }
    smoke_test.validate_tool_call(
        response,
        expected_name="get_weather",
        expected_arguments={"city": "Seoul"},
    )


def test_validate_tool_call_rejects_missing_call():
    with pytest.raises(ValueError, match="valid tool call"):
        smoke_test.validate_tool_call(
            {"choices": [{"message": {}}]},
            expected_name="get_weather",
            expected_arguments={"city": "Seoul"},
        )
