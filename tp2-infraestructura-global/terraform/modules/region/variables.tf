variable "name" {
  description = "Prefijo de nombres de recursos de la región"
  type        = string
}

variable "environment" {
  type = string
}

variable "vpc_cidr" {
  description = "Rango de IPs de la VPC (distinto por región para poder interconectarlas)"
  type        = string
}

variable "eks_min_nodes" {
  type = number
}

variable "eks_max_nodes" {
  type = number
}

variable "jwt_issuer" {
  type = string
}

variable "jwt_audience" {
  type = list(string)
}
