#
# Keycloak Application Load Balancer
#

resource "aws_lb" "keycloak" {
  name               = "keycloak-alb"
  internal           = false
  load_balancer_type = "application"

  drop_invalid_header_fields = true
  enable_deletion_protection = false

  security_groups = [aws_security_group.keycloak_lb.id]
  subnets         = module.vpc.public_subnets

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-alb"
    }
  )
}

# Random suffix for target group name (required by AWS)
resource "random_string" "alb_tg_suffix" {
  length  = 3
  special = false
  upper   = false
}

# Target Group
resource "aws_lb_target_group" "keycloak" {
  name                 = "keycloak-tg-${random_string.alb_tg_suffix.result}"
  port                 = 8080
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = module.vpc.vpc_id
  deregistration_delay = 30

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200-399"
    protocol            = "HTTP"
  }

  stickiness {
    type            = "lb_cookie"
    enabled         = true
    cookie_duration = 86400
  }

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-tg"
    }
  )

  lifecycle {
    create_before_destroy = true
    ignore_changes = [
      stickiness[0].cookie_name
    ]
  }
}

# HTTPS Listener
resource "aws_lb_listener" "keycloak_https" {
  load_balancer_arn = aws_lb.keycloak.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.keycloak.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.keycloak.arn
  }

  tags = local.common_tags
}

# HTTP to HTTPS Redirect Listener
resource "aws_lb_listener" "keycloak_http_redirect" {
  load_balancer_arn = aws_lb.keycloak.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }

  tags = local.common_tags
}
