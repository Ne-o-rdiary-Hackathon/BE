from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator


class ActivityItem(BaseModel):
    activity_id: int
    activity_name: str


class ActivitySubcategory(BaseModel):
    category_id: int
    category_name: str
    activities: list[ActivityItem]


class ActivityCategory(BaseModel):
    category_id: int
    category_name: str
    subcategories: list[ActivitySubcategory]


class ActivityCatalogResponse(BaseModel):
    categories: list[ActivityCategory]


class ActivitySubmissionRequest(BaseModel):
    desired_activity_ids: list[Annotated[int, Field(strict=True, gt=0)]]
    bored_activity_ids: list[Annotated[int, Field(strict=True, gt=0)]]

    @model_validator(mode="after")
    def validate_activity_selections(self) -> Self:
        desired = set(self.desired_activity_ids)
        bored = set(self.bored_activity_ids)
        if len(desired) != len(self.desired_activity_ids):
            raise ValueError("desired_activity_ids에 중복된 활동이 있습니다.")
        if len(bored) != len(self.bored_activity_ids):
            raise ValueError("bored_activity_ids에 중복된 활동이 있습니다.")
        if desired & bored:
            raise ValueError("같은 활동을 원하는 활동과 싫은 활동에 함께 선택할 수 없습니다.")
        return self


class ActivitySubmissionResponse(BaseModel):
    status: Literal["SUBMITTED"]
    all_members_submitted: bool
