from pydantic import BaseModel, Field
from typing import List, Optional

class CreateTopicRequest(BaseModel):
    Name: str = Field(..., description="Name of the SNS topic")

class CreateTopicResponse(BaseModel):
    TopicArn: str = Field(..., description="ARN of the created topic")

class PublishRequest(BaseModel):
    TopicArn: str = Field(..., description="ARN of the target topic")
    Message: str = Field(..., description="Message payload")
    Subject: Optional[str] = Field(None, description="Optional subject")

class PublishResponse(BaseModel):
    MessageId: str = Field(..., description="ID of the published message")

class SubscribeRequest(BaseModel):
    TopicArn: str = Field(..., description="ARN of the topic to subscribe to")
    Protocol: str = Field(..., description="Protocol (e.g., 'sqs', 'http')")
    Endpoint: str = Field(..., description="Endpoint URL or queue name")

class SubscribeResponse(BaseModel):
    SubscriptionArn: str = Field(..., description="ARN of the subscription")

class TopicInfo(BaseModel):
    TopicArn: str
    Owner: Optional[str] = None
    Attributes: Optional[dict] = None

class ListTopicsResponse(BaseModel):
    Topics: List[TopicInfo]

class SubscriptionInfo(BaseModel):
    SubscriptionArn: str
    Owner: Optional[str] = None
    Protocol: str
    Endpoint: str
    Attributes: Optional[dict] = None

class ListSubscriptionsResponse(BaseModel):
    Subscriptions: List[SubscriptionInfo]

class DeleteTopicRequest(BaseModel):
    TopicArn: str = Field(..., description="ARN of the topic to delete")

class DeleteTopicResponse(BaseModel):
    pass
