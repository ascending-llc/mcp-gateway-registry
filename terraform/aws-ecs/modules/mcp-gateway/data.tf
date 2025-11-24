# Data sources for MCP Gateway Registry Module

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

# Get VPC data
data "aws_vpc" "vpc" {
  id = var.vpc_id
}