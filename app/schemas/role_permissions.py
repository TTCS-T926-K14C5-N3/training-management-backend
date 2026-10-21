from pydantic import BaseModel, ConfigDict, Field


class RolePermissionsUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    permission_codes: list[str] = Field(alias="permissionCodes")
