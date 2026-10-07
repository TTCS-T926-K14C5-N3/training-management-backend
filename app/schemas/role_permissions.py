from pydantic import BaseModel, Field


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str] = Field(alias="permissionCodes")
