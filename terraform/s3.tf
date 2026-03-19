#############
# S3 Bucket
# Stores ingestion data for TTC
#############
resource "aws_s3_bucket" "ttc" {
  bucket = var.s3_bucket

  tags = local.tags
}
