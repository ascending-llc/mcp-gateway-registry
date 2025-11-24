# Networking resources for MCP Gateway Registry

# Service Discovery Namespace
resource "aws_service_discovery_private_dns_namespace" "mcp" {
  name        = "${local.name_prefix}.local"
  description = "Service discovery namespace for MCP Gateway Registry"
  vpc         = var.vpc_id
  tags        = local.common_tags
}

# Main Application Load Balancer (for registry, auth, gradio)
module "alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "~> 9.0"

  name                       = "${local.name_prefix}-alb"
  load_balancer_type         = "application"
  internal                   = var.alb_scheme == "internal"
  enable_deletion_protection = false

  vpc_id  = var.vpc_id
  subnets = var.alb_scheme == "internal" ? var.private_subnet_ids : var.public_subnet_ids

  # Security Groups
  # Create dynamic ingress rules for each CIDR block and port combination
  security_group_ingress_rules = merge([
    for idx, cidr in var.ingress_cidr_blocks : {
      "http_${idx}" = {
        from_port   = 80
        to_port     = 80
        ip_protocol = "tcp"
        cidr_ipv4   = cidr
      }
      "https_${idx}" = {
        from_port   = 443
        to_port     = 443
        ip_protocol = "tcp"
        cidr_ipv4   = cidr
      }
      "auth_port_${idx}" = {
        from_port   = 8888
        to_port     = 8888
        ip_protocol = "tcp"
        cidr_ipv4   = cidr
      }
      "gradio_port_${idx}" = {
        from_port   = 7860
        to_port     = 7860
        ip_protocol = "tcp"
        cidr_ipv4   = cidr
      }
    }
  ]...)
  security_group_egress_rules = {
    all = {
      ip_protocol = "-1"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  listeners = merge(
    {
      http = {
        port     = 80
        protocol = "HTTP"
        forward = {
          target_group_key = "registry"
        }
      }
      auth = {
        port            = 8888
        protocol        = var.certificate_arn != "" ? "HTTPS" : "HTTP"
        certificate_arn = var.certificate_arn != "" ? var.certificate_arn : null
        forward = {
          target_group_key = "auth"
        }
      }
      gradio = {
        port     = 7860
        protocol = "HTTP"
        forward = {
          target_group_key = "gradio"
        }
      }
    },
    var.certificate_arn != "" ? {
      https = {
        port            = 443
        protocol        = "HTTPS"
        certificate_arn = var.certificate_arn
        forward = {
          target_group_key = "registry"
        }
      }
    } : {}
  )

  target_groups = {
    registry = {
      backend_protocol                  = "HTTP"
      backend_port                      = 7860
      target_type                       = "ip"
      deregistration_delay              = 5
      load_balancing_cross_zone_enabled = true

      health_check = {
        enabled             = true
        healthy_threshold   = 2
        interval            = 30
        matcher             = "200"
        path                = "/health"
        port                = 7860
        protocol            = "HTTP"
        timeout             = 5
        unhealthy_threshold = 2
      }

      create_attachment = false
    }
    auth = {
      backend_protocol                  = "HTTP"
      backend_port                      = 8888
      target_type                       = "ip"
      deregistration_delay              = 5
      load_balancing_cross_zone_enabled = true

      health_check = {
        enabled             = true
        healthy_threshold   = 2
        interval            = 30
        matcher             = "200"
        path                = "/health"
        port                = "traffic-port"
        protocol            = "HTTP"
        timeout             = 5
        unhealthy_threshold = 2
      }

      create_attachment = false
    }
    gradio = {
      backend_protocol                  = "HTTP"
      backend_port                      = 7860
      target_type                       = "ip"
      deregistration_delay              = 5
      load_balancing_cross_zone_enabled = true

      health_check = {
        enabled             = true
        healthy_threshold   = 2
        interval            = 30
        matcher             = "200"
        path                = "/health"
        port                = "traffic-port"
        protocol            = "HTTP"
        timeout             = 5
        unhealthy_threshold = 2
      }

      create_attachment = false
    }
  }

  tags = local.common_tags
}
