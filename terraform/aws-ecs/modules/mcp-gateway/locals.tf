# Local values for MCP Gateway Registry Module

locals {
  name_prefix = var.name

  common_tags = merge(
    {
      stack     = var.name
      component = "mcp-gateway-registry"
    },
    var.additional_tags
  )
}