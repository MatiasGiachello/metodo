variable "environment" {
  description = "Entorno de despliegue (prod, staging)"
  type        = string
  default     = "prod"
}

variable "domain_name" {
  description = "Dominio raíz de la plataforma"
  type        = string
  default     = "pagoglobal.com"
}

variable "eks_min_nodes" {
  description = "Nodos mínimos de Kubernetes por región (subir antes de Black Friday)"
  type        = number
  default     = 6
}

variable "eks_max_nodes" {
  description = "Nodos máximos de Kubernetes por región (techo del autoscaling)"
  type        = number
  default     = 60
}

variable "jwt_issuer" {
  description = "Emisor de los JWT (servidor OAuth 2.0)"
  type        = string
  default     = "https://auth.pagoglobal.com"
}

variable "jwt_audience" {
  description = "Audiencia esperada en los JWT de la API pública"
  type        = list(string)
  default     = ["https://api.pagoglobal.com"]
}
