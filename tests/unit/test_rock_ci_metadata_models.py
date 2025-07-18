# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from pydantic import ValidationError

from charmed_analytics_ci.rock_ci_metadata_models import RockCIMetadata

VALID_METADATA = {
    "integrations": [
        {
            "consumer-repository": "https://github.com/canonical/kfp-operators",
            "replace-image": [
                {
                    "file": "charms/kfp-api/metadata.yaml",
                    "path": "resources.oci-image.upstream-source",
                },
                {"file": "charms/kfp-api/config.yaml", "path": "spec.containers[0].image"},
            ],
            "service-spec": [
                {
                    "file": "charms/kfp-api/service-config.yaml",
                    "user": {"path": "user", "value": "_daemon_"},
                    "command": {"path": "command", "value": "bash -c 'echo hello'"},
                }
            ],
        }
    ]
}


def test_valid_metadata():
    """Should validate with full valid structure."""
    RockCIMetadata.model_validate(VALID_METADATA)


def test_missing_integrations():
    """Should fail when 'integrations' is missing."""
    with pytest.raises(ValidationError, match=r"integrations\s*\n\s*Field required"):
        RockCIMetadata.model_validate({})


def test_empty_integrations():
    """Should fail when 'integrations' is an empty list."""
    with pytest.raises(ValidationError, match=r"List should have at least 1 item.*too_short"):
        RockCIMetadata.model_validate({"integrations": []})


def test_missing_replace_image():
    """Should fail when 'replace-image' is missing in integration."""
    data = {"integrations": [{"consumer-repository": "https://example.com/repo.git"}]}
    with pytest.raises(ValidationError, match=r"replace-image\s*\n\s*Field required"):
        RockCIMetadata.model_validate(data)


def test_service_spec_optional():
    """Should validate if service-spec is missing."""
    data = {
        "integrations": [
            {
                "consumer-repository": "https://example.com/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "some.path"}],
            }
        ]
    }
    RockCIMetadata.model_validate(data)


def test_service_spec_requires_user_or_command():
    """Should fail if service-spec is present but both 'user' and 'command' are missing."""
    data = {
        "integrations": [
            {
                "consumer-repository": "https://example.com/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "some.path"}],
                "service-spec": [{"file": "svc.yaml"}],
            }
        ]
    }
    with pytest.raises(ValidationError, match=r"At least one of 'user' or 'command'"):
        RockCIMetadata.model_validate(data)


def test_service_spec_with_only_user():
    """Should validate if service-spec contains only 'user' section."""
    data = {
        "integrations": [
            {
                "consumer-repository": "https://example.com/repo.git",
                "replace-image": [{"file": "file.yaml", "path": "some.path"}],
                "service-spec": [
                    {"file": "svc.yaml", "user": {"path": "user", "value": "ubuntu"}}
                ],
            }
        ]
    }
    RockCIMetadata.model_validate(data)


def test_invalid_property_in_root():
    """Should fail when there’s an unexpected top-level field."""
    data = {
        "integrations": VALID_METADATA["integrations"],
        "extra": "unexpected",
    }
    with pytest.raises(ValidationError, match=r"Extra inputs are not permitted"):
        RockCIMetadata.model_validate(data)
