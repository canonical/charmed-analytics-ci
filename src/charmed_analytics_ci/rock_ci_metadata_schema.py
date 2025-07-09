# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

rock_ci_metadata_schema = {
    "type": "object",
    "required": ["integrations"],
    "properties": {
        "integrations": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["consumer-repository", "replace-image"],
                "properties": {
                    "consumer-repository": {"type": "string", "minLength": 1},
                    "replace-image": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "required": ["file", "path"],
                            "properties": {
                                "file": {"type": "string", "minLength": 1},
                                "path": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "service-spec": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["file"],
                            "properties": {
                                "file": {"type": "string", "minLength": 1},
                                "user": {
                                    "type": "object",
                                    "required": ["path", "value"],
                                    "properties": {
                                        "path": {"type": "string", "minLength": 1},
                                        "value": {"type": "string"},
                                    },
                                },
                                "command": {
                                    "type": "object",
                                    "required": ["path", "value"],
                                    "properties": {
                                        "path": {"type": "string", "minLength": 1},
                                        "value": {"type": "string"},
                                    },
                                },
                            },
                            "anyOf": [{"required": ["user"]}, {"required": ["command"]}],
                        },
                    },
                },
            },
        }
    },
    "additionalProperties": False,
}
