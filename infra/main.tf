provider "aws" {
  region = var.aws_region
}

# 1. SQS Webhook Queue
resource "aws_sqs_queue" "webhook_queue" {
  name                      = "${var.project_name}-webhook-queue"
  delay_seconds             = 0
  max_message_size          = 262144
  message_retention_seconds = 86400
  receive_wait_time_seconds = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.webhook_queue_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "webhook_queue_dlq" {
  name = "${var.project_name}-webhook-queue-dlq"
}

# 2. DynamoDB Table for Budget & Cost tracking
resource "aws_dynamodb_table" "agent_budgets" {
  name         = "AgentBudgets"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "repo_name"
  range_key    = "date"

  attribute {
    name = "repo_name"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# 3. ECS Cluster
resource "aws_ecs_cluster" "agent_cluster" {
  name = "${var.project_name}-cluster"
}

# 4. IAM Roles for ECS Task execution
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.project_name}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# 5. CloudWatch Log Group
resource "aws_cloudwatch_log_group" "ecs_logs" {
  name              = "/ecs/${var.project_name}-worker"
  retention_in_days = 7
}

# 6. ECS Fargate Task Definition for the Agent Worker
resource "aws_ecs_task_definition" "worker_task" {
  family                   = "${var.project_name}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = "${var.worker_image_url}:latest"
      essential = true
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_logs.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }

      environment = [
        { name = "LLM_PROVIDER", value = "anthropic" },
        { name = "LLM_MODEL", value = "claude-3-5-sonnet-20241022" },
        { name = "GITHUB_APP_ID", value = var.github_app_id }
      ]
    }
  ])
}
