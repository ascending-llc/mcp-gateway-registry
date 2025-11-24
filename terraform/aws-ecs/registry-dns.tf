#
# Registry DNS and SSL Certificate Configuration
#
# Provides DNS and HTTPS support for the main MCP Gateway Registry ALB
# Domain: registry.mycorp.click (configured via local.root_domain)
#

# Use existing hosted zone for the root domain
data "aws_route53_zone" "registry_root" {
  name         = local.hosted_zone_domain
  private_zone = false
}

# Create SSL certificate for registry subdomain
resource "aws_acm_certificate" "registry" {
  domain_name       = "registry.${local.root_domain}"
  validation_method = "DNS"

  tags = merge(
    local.common_tags,
    {
      Name      = "registry-cert"
      Component = "registry"
    }
  )

  lifecycle {
    create_before_destroy = true
  }
}

# Create DNS validation records for ACM certificate
resource "aws_route53_record" "registry_certificate_validation" {
  for_each = {
    for dvo in aws_acm_certificate.registry.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.registry_root.zone_id
}

# Wait for certificate validation to complete
resource "aws_acm_certificate_validation" "registry" {
  certificate_arn = aws_acm_certificate.registry.arn

  timeouts {
    create = "5m"
  }

  validation_record_fqdns = [for record in aws_route53_record.registry_certificate_validation : record.fqdn]
}

# Create A record for registry subdomain pointing to main ALB
resource "aws_route53_record" "registry" {
  zone_id = data.aws_route53_zone.registry_root.zone_id
  name    = "registry.${local.root_domain}"
  type    = "A"

  alias {
    name                   = module.mcp_gateway.alb_dns_name
    zone_id                = module.mcp_gateway.alb_zone_id
    evaluate_target_health = true
  }
}
