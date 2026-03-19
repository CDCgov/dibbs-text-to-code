variable "region" {
  type    = string
  default = "us-east-2"
}

variable "state_bucket_name" {
  type    = string
  default = "dibbs-ttc-terraform-state"
}

variable "lock_table_name" {
  type    = string
  default = "dibbs-ttc-terraform-lock"
}
