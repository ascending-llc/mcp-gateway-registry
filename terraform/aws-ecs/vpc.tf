data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)

  # VPC endpoint service name prefix varies by partition and endpoint type
  # Gateway endpoints (S3, DynamoDB): com.amazonaws.{region}.{service} (same in all regions)
  # Interface endpoints (STS, etc):
  #   - Standard AWS: com.amazonaws.{region}.{service}
  #   - China regions: cn.com.amazonaws.{region}.{service}
  interface_endpoint_prefix = data.aws_partition.current.partition == "aws-cn" ? "cn.com.amazonaws" : "com.amazonaws"
  gateway_endpoint_prefix   = "com.amazonaws"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = "${var.name}-vpc"
  cidr = var.vpc_cidr

  azs             = local.azs
  private_subnets = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 4, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k + 48)]

  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  # VPC Flow Logs
  enable_flow_log = false

  # Tags for ECS and ALB usage
  private_subnet_tags = {
    "subnet-type" = "private"
  }

  public_subnet_tags = {
    "subnet-type" = "public"
  }
}

# VPC Endpoints for AWS services
resource "aws_vpc_endpoint" "sts" {
  vpc_id             = module.vpc.vpc_id
  service_name       = "${local.interface_endpoint_prefix}.${data.aws_region.current.region}.sts"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = module.vpc.private_subnets
  security_group_ids = [aws_security_group.vpc_endpoints.id]

  private_dns_enabled = true
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "${local.gateway_endpoint_prefix}.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}

# Security group for VPC endpoints
resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name}-vpc-endpoints"
  description = "Security group for VPC endpoints"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }
}