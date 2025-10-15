# LocalStackを使ってTerraformを実践してみた
## やり方
1. LocalStackをdocker composeで起動
```zsh
docker compose up -d
```
2. LocalStackにアクセス
```zsh
docker compose exec localstack /bin/bash
```
3. Terraformをインストール
```bash
apt-get update && apt-get install -y wget unzip
wget https://releases.hashicorp.com/terraform/1.8.1/terraform_1.8.1_linux_arm64.zip
unzip terraform_1.8.1_linux_arm64.zip
mv terraform /usr/local/bin/
terraform version
```
3. TerraformでAWSのリソースを作成  

workディレクトリを作成
```bash
mkdir -p /opt/code/localstack/terraform_work/01
cd /opt/code/localstack/terraform_work/01
``` 
以下のファイルを作成
```bash
cat > provider.tf
<下記のprovider.tfの内容をコピー＆ペーストした後、Ctrl+C>
ls -l provider.tf
cat > s3.tf
<下記のs3.tfの内容をコピー＆ペーストした後、Ctrl+C>
ls -l s3.tf
```
provider.tf
```hcl
terraform {
  required_version = "= 1.8.1"
  backend "local" {
    path = "/opt/code/localstack/terraform_work/terraform.tfstate"
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  s3_use_path_style           = true


  endpoints {
    s3       = "http://localhost:4566"
    iam      = "http://localhost:4566"
    dynamodb = "http://localhost:4566"
    lambda   = "http://localhost:4566"
    sts      = "http://localhost:4566"
  }
}
```
s3.tf
```hcl
resource "aws_s3_bucket" "example" {
  bucket = "my-test-bucket"
}
```
4. Terraform コマンドで実行＆確認
```bash
terraform init -upgrade
terraform fmt && terraform validate
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```
5. 作成したS3バケットの確認
```bash
awslocal s3 ls
```
## 注意点
無料版のLocalStackは永続サポートされていないので一度、docker compose downしてしまうと、作成したリソースは消えてしまう。
永続サポートしたい場合はPro版を購入する。
## 実行ログ
### Terraform コマンド実行とS3バケットの確認
```bash
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# terraform init -upgrade

Initializing the backend...

Successfully configured the backend "local"! Terraform will automatically
use this backend unless the backend configuration changes.

Initializing provider plugins...
- Finding latest version of hashicorp/aws...
- Using previously-installed hashicorp/aws v6.16.0

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# terraform fmt && terraform validate
Success! The configuration is valid.

root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# terraform plan -out=plan.tfplan

Terraform used the selected providers to generate the following execution plan. Resource actions are indicated with the following
symbols:
  + create

Terraform will perform the following actions:

  # aws_s3_bucket.example will be created
  + resource "aws_s3_bucket" "example" {
      + acceleration_status         = (known after apply)
      + acl                         = (known after apply)
      + arn                         = (known after apply)
      + bucket                      = "my-test-bucket"
      + bucket_domain_name          = (known after apply)
      + bucket_prefix               = (known after apply)
      + bucket_region               = (known after apply)
      + bucket_regional_domain_name = (known after apply)
      + force_destroy               = false
      + hosted_zone_id              = (known after apply)
      + id                          = (known after apply)
      + object_lock_enabled         = (known after apply)
      + policy                      = (known after apply)
      + region                      = "us-east-1"
      + request_payer               = (known after apply)
      + tags_all                    = (known after apply)
      + website_domain              = (known after apply)
      + website_endpoint            = (known after apply)
    }

Plan: 1 to add, 0 to change, 0 to destroy.

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

Saved the plan to: plan.tfplan

To perform exactly these actions, run the following command to apply:
    terraform apply "plan.tfplan"
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# terraform apply "plan.tfplan"
aws_s3_bucket.example: Creating...
aws_s3_bucket.example: Creation complete after 0s [id=my-test-bucket]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# ls -l ../
total 8
drwxr-xr-x 3 root root 4096 Oct 15 17:43 01
-rw-r--r-- 1 root root 2646 Oct 15 17:58 terraform.tfstate
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# awslocal s3 ls
2025-10-15 17:58:30 my-test-bucket
2025-10-15 12:15:11 test2-bucket
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
```
### terraform.tfstateの確認
```bash
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# cat ../terraform.tfstate
{
  "version": 4,
  "terraform_version": "1.8.1",
  "serial": 1,
  "lineage": "2c848a11-6bc9-6bb6-98f1-a20add110861",
  "outputs": {},
  "resources": [
    {
      "mode": "managed",
      "type": "aws_s3_bucket",
      "name": "example",
      "provider": "provider[\"registry.terraform.io/hashicorp/aws\"]",
      "instances": [
        {
          "schema_version": 0,
          "attributes": {
            "acceleration_status": "",
            "acl": null,
            "arn": "arn:aws:s3:::my-test-bucket",
            "bucket": "my-test-bucket",
            "bucket_domain_name": "my-test-bucket.s3.amazonaws.com",
            "bucket_prefix": "",
            "bucket_region": "us-east-1",
            "bucket_regional_domain_name": "my-test-bucket.s3.us-east-1.amazonaws.com",
            "cors_rule": [],
            "force_destroy": false,
            "grant": [
              {
                "id": "75aa57f09aa0c8caeab4f8c24e99d10f8e7faeebf76c078efc7c6caea54ba06a",
                "permissions": [
                  "FULL_CONTROL"
                ],
                "type": "CanonicalUser",
                "uri": ""
              }
            ],
            "hosted_zone_id": "Z3AQBSTGFYJSTF",
            "id": "my-test-bucket",
            "lifecycle_rule": [],
            "logging": [],
            "object_lock_configuration": [],
            "object_lock_enabled": false,
            "policy": "",
            "region": "us-east-1",
            "replication_configuration": [],
            "request_payer": "BucketOwner",
            "server_side_encryption_configuration": [
              {
                "rule": [
                  {
                    "apply_server_side_encryption_by_default": [
                      {
                        "kms_master_key_id": "",
                        "sse_algorithm": "AES256"
                      }
                    ],
                    "bucket_key_enabled": false
                  }
                ]
              }
            ],
            "tags": null,
            "tags_all": {},
            "timeouts": null,
            "versioning": [
              {
                "enabled": false,
                "mfa_delete": false
              }
            ],
            "website": [],
            "website_domain": null,
            "website_endpoint": null
          },
          "sensitive_attributes": [],
          "private": "eyJlMmJmYjczMC1lY2FhLTExZTYtOGY4OC0zNDM2M2JjN2M0YzAiOnsiY3JlYXRlIjoxMjAwMDAwMDAwMDAwLCJkZWxldGUiOjM2MDAwMDAwMDAwMDAsInJlYWQiOjEyMDAwMDAwMDAwMDAsInVwZGF0ZSI6MTIwMDAwMDAwMDAwMH19"
        }
      ]
    }
  ],
  "check_results": null
}
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#
```
変更ないと以下のように出力される。
```bash
root@8a49b386aa39:/opt/code/localstack/terraform_work/01# terraform plan -out=plan_after.tfplan
aws_s3_bucket.example: Refreshing state... [id=my-test-bucket]

No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration and found no differences, so no changes are needed.
root@8a49b386aa39:/opt/code/localstack/terraform_work/01#

```

