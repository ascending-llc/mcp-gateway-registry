#
# Keycloak Security Groups
#

# ECS Security Group
resource "aws_security_group" "keycloak_ecs" {
  name        = "keycloak-ecs"
  description = "Security group for Keycloak ECS tasks"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-ecs"
    }
  )
}

# ECS Egress to Internet (HTTPS)
resource "aws_security_group_rule" "keycloak_ecs_egress_internet" {
  description       = "Egress from Keycloak ECS task to internet (HTTPS)"
  type              = "egress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.keycloak_ecs.id
}

# ECS Egress to DNS
resource "aws_security_group_rule" "keycloak_ecs_egress_dns" {
  description       = "Egress from Keycloak ECS task for DNS"
  type              = "egress"
  from_port         = 53
  to_port           = 53
  protocol          = "udp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.keycloak_ecs.id
}

# ECS Egress to Database
resource "aws_security_group_rule" "keycloak_ecs_egress_db" {
  description              = "Egress from Keycloak ECS task to database"
  type                     = "egress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_ecs.id
  source_security_group_id = aws_security_group.keycloak_db.id
}

# ECS Ingress from Load Balancer
resource "aws_security_group_rule" "keycloak_ecs_ingress_lb" {
  description              = "Ingress from load balancer to Keycloak ECS task"
  type                     = "ingress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_ecs.id
  source_security_group_id = aws_security_group.keycloak_lb.id
}

# Load Balancer Security Group
resource "aws_security_group" "keycloak_lb" {
  name        = "keycloak-lb"
  description = "Security group for Keycloak load balancer"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-lb"
    }
  )
}

# Load Balancer Ingress from allowed CIDR blocks (HTTP)
resource "aws_security_group_rule" "keycloak_lb_ingress_http" {
  description       = "Ingress from allowed CIDR blocks to load balancer (HTTP)"
  type              = "ingress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = var.ingress_cidr_blocks
  security_group_id = aws_security_group.keycloak_lb.id
}

# Load Balancer Ingress from allowed CIDR blocks (HTTPS)
resource "aws_security_group_rule" "keycloak_lb_ingress_https" {
  description       = "Ingress from allowed CIDR blocks to load balancer (HTTPS)"
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = var.ingress_cidr_blocks
  security_group_id = aws_security_group.keycloak_lb.id
}

# Load Balancer Ingress from MCP Gateway Auth Server (HTTPS)
# Note: This rule is for direct VPC traffic. For traffic via NAT gateway,
# see keycloak_lb_ingress_nat_gateway rule below.
resource "aws_security_group_rule" "keycloak_lb_ingress_auth_server" {
  description              = "Ingress from MCP Gateway Auth Server to Keycloak load balancer (HTTPS)"
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_lb.id
  source_security_group_id = module.mcp_gateway.ecs_security_group_ids.auth
}

# Load Balancer Ingress from NAT Gateways (for ECS tasks making HTTPS requests to Keycloak public URL)
# When ECS tasks in private subnets call Keycloak's public DNS name, traffic goes through NAT gateway.
# The source IP becomes the NAT gateway's public IP, not the ECS task's security group.
resource "aws_security_group_rule" "keycloak_lb_ingress_nat_gateway" {
  description       = "Ingress from NAT gateways to Keycloak load balancer (HTTPS)"
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = [for ip in module.vpc.nat_public_ips : "${ip}/32"]
  security_group_id = aws_security_group.keycloak_lb.id
}

# Load Balancer Ingress from MCP Gateway Registry (HTTPS)
resource "aws_security_group_rule" "keycloak_lb_ingress_registry" {
  description              = "Ingress from MCP Gateway Registry to Keycloak load balancer (HTTPS)"
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_lb.id
  source_security_group_id = module.mcp_gateway.ecs_security_group_ids.registry
}

# Load Balancer Egress to ECS
resource "aws_security_group_rule" "keycloak_lb_egress_ecs" {
  description              = "Egress from load balancer to Keycloak ECS task"
  type                     = "egress"
  from_port                = 8080
  to_port                  = 8080
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_lb.id
  source_security_group_id = aws_security_group.keycloak_ecs.id
}

# Database Security Group
resource "aws_security_group" "keycloak_db" {
  name        = "keycloak-db"
  description = "Security group for Keycloak database"
  vpc_id      = module.vpc.vpc_id

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-db"
    }
  )
}

# Database Ingress from ECS
resource "aws_security_group_rule" "keycloak_db_ingress_ecs" {
  description              = "Ingress to database from Keycloak ECS task"
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_db.id
  source_security_group_id = aws_security_group.keycloak_ecs.id
}

# Database Ingress from RDS Proxy
resource "aws_security_group_rule" "keycloak_db_ingress_proxy" {
  description              = "Ingress to database from RDS Proxy"
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.keycloak_db.id
  source_security_group_id = aws_security_group.keycloak_db.id
}
