import json
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.errors import agents as agent_errors


def test_raise_problem_serializes_uuid_extensions():
    sample_uuid = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        agent_errors.raise_problem(
            status_code=400,
            title="Bad Request",
            detail="Example",
            extensions={"session_id": sample_uuid},
        )

    payload = exc_info.value.detail
    assert payload["extensions"]["session_id"] == str(sample_uuid)

    # Ensure payload can be JSON encoded without custom encoders
    json.dumps(payload)


def test_session_not_found_uses_serializable_detail():
    sample_uuid = str(uuid4())

    with pytest.raises(HTTPException) as exc_info:
        agent_errors.session_not_found(sample_uuid)

    payload = exc_info.value.detail
    assert payload["extensions"]["session_id"] == sample_uuid
    json.dumps(payload)
