variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS Deployment Region"
}

variable "project_name" {
  type        = string
  default     = "github-pr-agent"
  description = "Name of the project used for tagging resources"
}

variable "environment" {
  type        = string
  default     = "production"
  description = "Target deployment environment"
}

variable "github_app_id" {
  type        = string
  default     = "123456"
  description = "GitHub App Issuer ID"
}

variable "worker_image_url" {
  type        = string
  default     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/github-pr-agent-worker"
  description = "Docker image repository URL for the worker"
}
