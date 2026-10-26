# =============================================================================
# PagoGlobal - Infraestructura global (3 regiones) con Terraform
# TP2 - Plataformas de Pagos Electrónicos
#
# Uso:
#   terraform init
#   terraform plan  -var-file=prod.tfvars
#   terraform apply -var-file=prod.tfvars
# =============================================================================

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # El estado se guarda cifrado en S3 con bloqueo en DynamoDB:
  # evita que dos personas apliquen cambios al mismo tiempo.
  backend "s3" {
    bucket         = "pagoglobal-terraform-state"
    key            = "global/prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "pagoglobal-terraform-locks"
  }
}

# -----------------------------------------------------------------------------
# Un provider por región (alias). CloudFront y ACM globales viven en us-east-1.
# -----------------------------------------------------------------------------
provider "aws" {
  alias  = "us"
  region = "us-east-1"
  default_tags { tags = local.tags }
}

provider "aws" {
  alias  = "sa"
  region = "sa-east-1"
  default_tags { tags = local.tags }
}

provider "aws" {
  alias  = "eu"
  region = "eu-west-1"
  default_tags { tags = local.tags }
}

locals {
  tags = {
    Proyecto     = "PagoGlobal"
    Entorno      = var.environment
    Gestionado   = "terraform"
    Cumplimiento = "pci-dss"
  }
}

# -----------------------------------------------------------------------------
# El mismo módulo se instancia en las 3 regiones: infraestructura idéntica,
# reproducible y auditable (la ventaja central de IaC para un sitio global).
# -----------------------------------------------------------------------------
module "region_us" {
  source    = "./modules/region"
  providers = { aws = aws.us }

  name          = "pagoglobal-us"
  environment   = var.environment
  vpc_cidr      = "10.20.0.0/16"
  eks_min_nodes = var.eks_min_nodes
  eks_max_nodes = var.eks_max_nodes
  jwt_issuer    = var.jwt_issuer
  jwt_audience  = var.jwt_audience
}

module "region_sa" {
  source    = "./modules/region"
  providers = { aws = aws.sa }

  name          = "pagoglobal-sa"
  environment   = var.environment
  vpc_cidr      = "10.10.0.0/16"
  eks_min_nodes = var.eks_min_nodes
  eks_max_nodes = var.eks_max_nodes
  jwt_issuer    = var.jwt_issuer
  jwt_audience  = var.jwt_audience
}

module "region_eu" {
  source    = "./modules/region"
  providers = { aws = aws.eu }

  name          = "pagoglobal-eu"
  environment   = var.environment
  vpc_cidr      = "10.30.0.0/16"
  eks_min_nodes = var.eks_min_nodes
  eks_max_nodes = var.eks_max_nodes
  jwt_issuer    = var.jwt_issuer
  jwt_audience  = var.jwt_audience
}
