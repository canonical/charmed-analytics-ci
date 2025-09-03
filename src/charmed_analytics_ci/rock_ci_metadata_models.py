# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReplaceImageEntry(BaseModel):
    """
    Represents a target location in a file where a container image reference should be replaced.

    Attributes:
        file (Path): Path to the file containing the image reference.
        path (str): JSONPath-style path within the file where the image reference resides.
    """

    model_config = ConfigDict(extra="forbid")

    file: Path
    path: str = Field(min_length=1)


class PathValue(BaseModel):
    """
    Represents a path and corresponding value for updating a service spec.

    Attributes:
        path (str): The key or location (typically a JSON path) to modify.
        value (str): The value to insert or update at the specified path.
    """

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    value: str


class ServiceSpecEntry(BaseModel):
    """
    Represents a change to be made to a service spec file.

    Attributes:
        file (Path): The service spec file to modify.
        user (Optional[PathValue]): Optional modification to the user field.
        command (Optional[PathValue]): Optional modification to the command field.
    """

    model_config = ConfigDict(extra="forbid")

    file: Path
    user: Optional[PathValue] = None
    command: Optional[PathValue] = None

    @model_validator(mode="after")
    def check_user_or_command(self) -> "ServiceSpecEntry":
        """
        Ensure that at least one of 'user' or 'command' is specified.

        Returns:
            ServiceSpecEntry: The validated model instance.

        Raises:
            ValueError: If both 'user' and 'command' are missing.
        """
        if not self.user and not self.command:
            raise ValueError("At least one of 'user' or 'command' must be specified.")
        return self


class IntegrationEntry(BaseModel):
    """
    Defines configuration for integrating with a consumer repository.

    Attributes:
        consumer_repository (str): The name of the target consumer repository.
        replace_image (List[ReplaceImageEntry]): List of image replacements to apply.
        service_spec (Optional[List[ServiceSpecEntry]]): Optional service spec updates.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        frozen=True,
    )

    consumer_repository: str = Field(alias="consumer-repository", min_length=1)
    replace_image: List[ReplaceImageEntry] = Field(alias="replace-image", min_length=1)
    service_spec: Optional[List[ServiceSpecEntry]] = Field(
        default_factory=list, alias="service-spec"
    )


class RockCIMetadata(BaseModel):
    """
    The root model for Rock CI metadata configuration.

    Attributes:
        integrations (List[IntegrationEntry]): List of integration configurations.
    """

    model_config = ConfigDict(extra="forbid")

    integrations: List[IntegrationEntry] = Field(min_length=0)
