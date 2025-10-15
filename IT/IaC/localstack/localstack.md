# LocalStack
<!-- TOC -->
* [LocalStack](#localstack)
  * [LocalStackとは](#localstackとは)
  * [インストール方法](#インストール方法)
    * [手順](#手順)
      * [今回の環境](#今回の環境)
      * [1. docker composeのインストール](#1-docker-composeのインストール-)
      * [2. docker composeファイルの作成](#2-docker-composeファイルの作成)
      * [3. LocalStack起動](#3-localstack起動)
      * [4. LocalStackにアクセスする](#4-localstackにアクセスする)
      * [5. pythonのバージョン確認＆pipバージョン確認](#5-pythonのバージョン確認pipバージョン確認)
      * [6. awscliのバージョン確認](#6-awscliのバージョン確認)
      * [7. awscli-localのインストール](#7-awscli-localのインストール)
      * [8. LocalStackのサービス確認  （今回はDynamoDB）](#8-localstackのサービス確認-今回はdynamodb)
  * [LocalStackでのAWSのリソース構築](#localstackでのawsのリソース構築)
    * [S3バケット作成と確認](#s3バケット作成と確認)
    * [DynamoDBのテーブル作成](#dynamodbのテーブル作成)
<!-- TOC -->
## LocalStackとは
AWSの環境をローカル端末で擬似的に再現できるモジュール。  
LocalStackを使用することで、AWSのサービスをローカルでテスト・開発できる。  
これにより、クラウド環境を使用せずに開発が可能となり、コスト削減や迅速な開発が実現できる。  
LocalStackにはcommunity版とPro版が存在して、Pro版は有料であるが、より多くのサービスをサポートしている。  
  
公式サイト: https://localstack.cloud/

## インストール方法
公式サイトにいくつか乗っているが今回はdocker composeを使用した方法を紹介する。
今回は以下のサイトを参考にした。  
- https://qiita.com/ryamate/items/fb9bd0bed550cdbe118b

### 手順
#### 今回の環境
```angular2html
- OS: MacOS Sequoia 15.7.1
- LauncherDesktop: 1.19.3
```
#### 1. docker composeのインストール  
割愛
#### 2. docker composeファイルの作成
以下のdocker-compose.ymlを作成する。  
参考：https://docs.localstack.cloud/aws/getting-started/installation/#starting-localstack-with-docker-compose

```yaml:docker-compose.yml
services:
  localstack:
    container_name: "${LOCALSTACK_DOCKER_NAME:-localstack-main}"
    image: localstack/localstack
    ports:
      - "127.0.0.1:4566:4566"            # LocalStack Gateway
      - "127.0.0.1:4510-4559:4510-4559"  # external services port range
    environment:
      # LocalStack configuration: https://docs.localstack.cloud/references/configuration/
      - DEBUG=${DEBUG:-0}
    volumes:
      - "${LOCALSTACK_VOLUME_DIR:-./volume}:/var/lib/localstack"
      - "/var/run/docker.sock:/var/run/docker.sock"
```
#### 3. LocalStack起動
```zsh
% docker compose up
[+] Running 2/2
 ✔ Network localstack_default  Created                                                                                        0.1s
 ✔ Container localstack-main   Created                                                                                        0.1s
Attaching to localstack-main
localstack-main  |
localstack-main  | LocalStack version: 4.9.1
localstack-main  | LocalStack build date: 2025-10-03
localstack-main  | LocalStack build git hash: 30111e0c9
localstack-main  |
localstack-main  | Ready.
```
#### 4. LocalStackにアクセスする
```zsh
% docker compose exec localstack /bin/bash
root@8a49b386aa39:/opt/code/localstack#
```
#### 5. pythonのバージョン確認＆pipバージョン確認
```bash
root@8a49b386aa39:/opt/code/localstack#
root@8a49b386aa39:/opt/code/localstack# python -V
Python 3.13.7
root@8a49b386aa39:/opt/code/localstack# pip -V
pip 25.2 from /usr/local/lib/python3.13/site-packages/pip (python 3.13)
root@8a49b386aa39:/opt/code/localstack# 
```
#### 6. awscliのバージョン確認
```bash
root@8a49b386aa39:/opt/code/localstack# aws --version
aws-cli/1.42.33 Python/3.13.7 Linux/6.6.93-0-virt botocore/1.40.33
root@8a49b386aa39:/opt/code/localstack#
root@8a49b386aa39:/opt/code/localstack#
root@8a49b386aa39:/opt/code/localstack# pip list | grep aws
awscli             1.42.33
awscli-local       0.22.2
root@8a49b386aa39:/opt/code/localstack#
```
#### 7. awscli-localのインストール
awscli-localはLocalstack用のawscliラッパーで、awsコマンドをawslocalコマンドに置き換えるだけで、Localstackに対してコマンドを実行できるようになる。  
```bash
root@8a49b386aa39:/opt/code/localstack# pip show awscli-local
Name: awscli-local
Version: 0.22.2
Summary: Thin wrapper around the "aws" command line interface for use with LocalStack
Home-page: https://github.com/localstack/awscli-local
Author: LocalStack Team
Author-email: info@localstack.cloud
License: Apache License 2.0
Location: /usr/local/lib/python3.13/site-packages
Requires: localstack-client
Required-by:
root@8a49b386aa39:/opt/code/localstack#
```
#### 8. LocalStackのサービス確認  （今回はDynamoDB）
```bash
root@8a49b386aa39:/opt/code/localstack# awslocal dynamodb list-tables
{
    "TableNames": []
}
root@8a49b386aa39:/opt/code/localstack#
```
ちなみにawsclilocalコマンドを使わないで、awsコマンドで実行する場合は、エンドポイントを指定する必要がある。  
```bash
root@8a49b386aa39:/opt/code/localstack# aws configure
AWS Access Key ID [None]: dummy
AWS Secret Access Key [None]: dummy
Default region name [None]: us-east-1
Default output format [None]: json
root@8a49b386aa39:/opt/code/localstack#
root@8a49b386aa39:/opt/code/localstack# aws --endpoint-url=http://localhost:4566 dynamodb list-tables
{
    "TableNames": []
}
root@8a49b386aa39:/opt/code/localstack#
``` 

## LocalStackでのAWSのリソース構築
参考：https://qiita.com/yasomaru/items/fa708a1f21a79e637868
### S3バケット作成と確認
参考: https://docs.localstack.cloud/aws/services/s3/
```bash
awslocal s3api create-bucket --bucket <バケット名>
```
```bash
root@8a49b386aa39:/opt/code/localstack# awslocal s3api create-bucket --bucket test2-bucket
{
    "Location": "/test2-bucket"
}
root@8a49b386aa39:/opt/code/localstack# awslocal s3 ls
2025-10-15 11:48:21 test-bucket
2025-10-15 11:53:27 test2-bucket
root@8a49b386aa39:/opt/code/localstack#
```
### DynamoDBのテーブル作成
参考：https://docs.localstack.cloud/aws/services/dynamodb/
```bash
awslocal dynamodb create-table --table-name <テーブル名> --attribute-definitions AttributeName=Id,AttributeType=S --key-schema AttributeName=Id,KeyType=HASH --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
```
