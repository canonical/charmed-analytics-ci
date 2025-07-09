# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import jsonschema
import pytest
from jsonschema import validate

from charmed_analytics_ci.rock_ci_metadata_schema import rock_ci_metadata_schema

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
    validate(instance=VALID_METADATA, schema=rock_ci_metadata_schema)


def test_missing_integrations():
    """Should fail when 'integrations' is missing."""
    with pytest.raises(jsonschema.ValidationError):
        validate(instance={}, schema=rock_ci_metadata_schema)


def test_empty_integrations():
    """Should fail when 'integrations' is an empty list."""
    data = {"integrations": []}
    with pytest.raises(jsonschema.ValidationError):
        validate(instance=data, schema=rock_ci_metadata_schema)


def test_missing_replace_image():
    """Should fail when 'replace-image' is missing in integration."""
    data = {"integrations": [{"consumer-repository": "https://example.com/repo.git"}]}
    with pytest.raises(jsonschema.ValidationError):
        validate(instance=data, schema=rock_ci_metadata_schema)


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
    validate(instance=data, schema=rock_ci_metadata_schema)


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
    with pytest.raises(jsonschema.ValidationError):
        validate(instance=data, schema=rock_ci_metadata_schema)


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
    validate(instance=data, schema=rock_ci_metadata_schema)


def test_invalid_property_in_root():
    """Should fail when there’s an unexpected top-level field."""
    data = {"integrations": VALID_METADATA["integrations"], "extra": "unexpected"}
    with pytest.raises(jsonschema.ValidationError):
        validate(instance=data, schema=rock_ci_metadata_schema)
