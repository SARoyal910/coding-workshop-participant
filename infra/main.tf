resource "random_id" "this" {
  byte_length = 4

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

resource "random_pet" "this" {
  length    = 3
  separator = "-"

  keepers = {
    seed_input = try(var.aws_app_code, terraform.workspace)
  }
}

# Generated once and kept in state, so tokens and demo logins survive redeploys.
resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "random_password" "seed_password" {
  length  = 16
  special = false
}
