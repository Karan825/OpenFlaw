import os
import json
import logging
from datetime import datetime
import boto3

logger = logging.getLogger(__name__)

# DynamoDB & ECS environment variables
BUDGET_TABLE = os.environ.get("BUDGET_TABLE_NAME", "AgentBudgets")
ECS_CLUSTER = os.environ.get("ECS_CLUSTER_NAME")
ECS_TASK_DEFINITION = os.environ.get("ECS_TASK_DEFINITION")
SUBNETS = os.environ.get("SUBNETS", "").split(",")
SECURITY_GROUPS = os.environ.get("SECURITY_GROUPS", "").split(",")
DAILY_PR_LIMIT = int(os.environ.get("DAILY_PR_LIMIT", 5))

# Initialize AWS resource clients
dynamodb = boto3.resource("dynamodb")
ecs = boto3.client("ecs")

def check_budget_and_dispatch(event, context):
    """
    AWS Lambda SQS handler. Processes queued triggers, checks budget limits in DynamoDB,
    and runs ECS Fargate tasks with override payloads.
    """
    for record in event["Records"]:
        body = record["body"]
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Failed to decode record body JSON.")
            continue
            
        repo_full_name = payload.get("repo_full_name")
        if not repo_full_name:
            logger.warning("SQS record is missing repo_full_name parameter.")
            continue
            
        # 1. Enforce per-repo budget ceiling per day in DynamoDB
        today = datetime.utcnow().strftime("%Y-%m-%d")
        table = dynamodb.Table(BUDGET_TABLE)
        
        try:
            response = table.get_item(Key={"repo_name": repo_full_name, "date": today})
            item = response.get("Item", {})
            pr_count = int(item.get("count_prs", 0))
        except Exception as e:
            logger.error(f"Error querying budget database for {repo_full_name}: {e}")
            pr_count = 0  # Fallback: assume 0 to prevent deployment lockups
            
        if pr_count >= DAILY_PR_LIMIT:
            logger.warning(f"Daily execution ceiling reached for {repo_full_name} on {today}. PR Count: {pr_count}/{DAILY_PR_LIMIT}. Aborting.")
            continue
            
        # 2. Dispatch ECS Fargate worker task
        logger.info(f"Dispatching ECS Fargate coding task for {repo_full_name} on branch fix")
        try:
            # Overrides container parameters to inject the specific SQS message body payload
            container_override = {
                "name": "worker",
                "environment": [
                    {"name": "PAYLOAD", "value": body}
                ]
            }
            
            response = ecs.run_task(
                cluster=ECS_CLUSTER,
                launchType="FARGATE",
                taskDefinition=ECS_TASK_DEFINITION,
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": SUBNETS,
                        "securityGroups": SECURITY_GROUPS,
                        "assignPublicIp": "ENABLED"
                    }
                },
                overrides={
                    "containerOverrides": [container_override]
                }
            )
            logger.info(f"ECS task successfully triggered: {response['tasks'][0]['taskArn']}")
            
            # 3. Update execution tracking counts in DynamoDB
            table.update_item(
                Key={"repo_name": repo_full_name, "date": today},
                UpdateExpression="ADD count_prs :inc",
                ExpressionAttributeValues={":inc": 1}
            )
            
        except Exception as e:
            logger.error(f"Failed to dispatch ECS Fargate task: {e}")
            raise e
            
    return {"status": "completed"}
