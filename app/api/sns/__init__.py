from fastapi import APIRouter, HTTPException
from .models import CreateTopicRequest, CreateTopicResponse, PublishRequest, PublishResponse, SubscribeRequest, SubscribeResponse, ListTopicsResponse, ListSubscriptionsResponse, DeleteTopicRequest, DeleteTopicResponse
from .service import sns_service

router = APIRouter(prefix="/sns", tags=["sns"])

@router.post("/CreateTopic", response_model=CreateTopicResponse)
async def create_topic(req: CreateTopicRequest):
    topic_arn = await sns_service.create_topic(req.Name)
    return CreateTopicResponse(TopicArn=topic_arn)

@router.post("/Publish", response_model=PublishResponse)
async def publish(req: PublishRequest):
    message_id = await sns_service.publish(req.TopicArn, req.Message)
    return PublishResponse(MessageId=message_id)

@router.post("/Subscribe", response_model=SubscribeResponse)
async def subscribe(req: SubscribeRequest):
    subscription_arn = await sns_service.subscribe(req.TopicArn, req.Protocol, req.Endpoint)
    return SubscribeResponse(SubscriptionArn=subscription_arn)

@router.get("/ListTopics", response_model=ListTopicsResponse)
async def list_topics():
    topics = await sns_service.list_topics()
    return ListTopicsResponse(Topics=topics)

@router.get("/ListSubscriptions", response_model=ListSubscriptionsResponse)
async def list_subscriptions():
    subs = await sns_service.list_subscriptions()
    return ListSubscriptionsResponse(Subscriptions=subs)

@router.post("/DeleteTopic", response_model=DeleteTopicResponse)
async def delete_topic(req: DeleteTopicRequest):
    await sns_service.delete_topic(req.TopicArn)
    return DeleteTopicResponse()
