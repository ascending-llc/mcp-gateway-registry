#
# Keycloak DNS and SSL Certificate
#

# Use existing hosted zone for the root domain
data "aws_route53_zone" "root" {
  name         = local.hosted_zone_domain
  private_zone = false
}

# Create SSL certificate for Keycloak domain
resource "aws_acm_certificate" "keycloak" {
  domain_name       = local.keycloak_domain
  validation_method = "DNS"

  tags = merge(
    local.common_tags,
    {
      Name = "keycloak-cert"
    }
  )

  lifecycle {
    create_before_destroy = true
  }
}

# Create DNS validation records
resource "aws_route53_record" "keycloak_certificate_validation" {
  for_each = {
    for dvo in aws_acm_certificate.keycloak.domain_validation_options : dvo.domain_name => {
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
  zone_id         = data.aws_route53_zone.root.zone_id
}

# Wait for certificate validation
resource "aws_acm_certificate_validation" "keycloak" {
  certificate_arn = aws_acm_certificate.keycloak.arn
  timeouts {
    create = "5m"
  }
  validation_record_fqdns = [for record in aws_route53_record.keycloak_certificate_validation : record.fqdn]
}

# Create A record for Keycloak subdomain
resource "aws_route53_record" "keycloak" {
  zone_id = data.aws_route53_zone.root.zone_id
  name    = local.keycloak_domain
  type    = "A"

  alias {
    name                   = aws_lb.keycloak.dns_name
    zone_id                = aws_lb.keycloak.zone_id
    evaluate_target_health = true
  }
}
