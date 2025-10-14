# Terraform 
<!-- TOC -->
* [Terraform](#terraform-)
  * [Terraformとは](#terraformとは)
    * [概要](#概要)
    * [特徴](#特徴)
    * [基本的なコマンド](#基本的なコマンド)
    * [HCLについて](#hclについて)
      * [terraform block](#terraform-block)
      * [provider](#provider)
      * [resource](#resource)
      * [variable](#variable)
      * [output](#output)
    * [各プロバイダーのリソースを作成](#各プロバイダーのリソースを作成)
      * [AWS](#aws)
      * [GCP](#gcp)
    * [まとめ](#まとめ)
  * [規模による使い分け](#規模による使い分け)
    * [小規模構成](#小規模構成)
* [参考](#参考)
<!-- TOC -->
## Terraformとは
### 概要
Terraformは、HashiCorpによって開発されたオープンソースのインフラストラクチャ自動化ツール。  
コードを使用してインフラストラクチャを定義、提供、管理が可能で、インフラストラクチャの構築、変更、バージョン管理が容易になる。  
  
[TerraFormの公式サイト](https://developer.hashicorp.com/terraform)
### 特徴
- **Infrastructure as Code (IaC)**: インフラストラクチャをコードとして定義し、バージョン管理が可能。
- **プロバイダーのサポート**: AWS、Azure、Google Cloudなど、多くのクラウドプロバイダーをサポート。
- **宣言的な構成**: ユーザーは望む最終状態を定義し、Terraformがその状態に到達するための手順を自動的に計算。
- **プランニング機能**: 変更を適用する前に、どのような変更が行われるかをプレビューすることができる。
- **モジュール化**: 再利用可能なコードブロックを作成し、複雑なインフラストラクチャを簡素化する。
### 基本的なコマンド
| コマンド              | 説明                                                         |
|----------------------|--------------------------------------------------------------|
| `terraform init`     | 新しいまたは既存のTerraform構成を初期化します。              |
| `terraform plan`     | 変更を適用する前に、どのような変更が行われるかをプレビューします。|
| `terraform apply`    | 構成に基づいてインフラストラクチャを作成または変更します。    |
| `terraform destroy`  | 作成したインフラストラクチャを削除します。                    |

### HCLについて
- provider、resource、variable、outputなどのブロックで構成される。
- ファイル拡張子は`.tf`。terraform.tfvars`は変数定義用。
- terraformコマンドを実行する場合、実行する配下にあるtfファイルをすべて読み込む。
- terraform ファイル名についてはどんな名称をつけても問題なし。
- tfファイルをすべてと見込み、構文解析を行い自動的に結合する。  
例
```hcl
provider "aws" {
  region = "us-west-2"
}
resource "aws_instance" "example" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"

  tags = {
    Name = "ExampleInstance"
  }
}
```
#### terraform block
Terraformのバージョンやバックエンド設定を指定。
```
terraform {`
  required_version = ">= 0.12" # Terraformのバージョン指定
  backend "s3" {
    bucket = "my-terraform-state"  # S3バケット名
    key    = "path/to/my/key" # 状態ファイルの保存パス
    region = "us-west-2" # バケットのリージョン
    dynamodb_table = "my-lock-table" # ロック用のDynamoDBテーブル名
  }
}
```
- Terraformのバージョンはローカル端末でもリモート環境でも合わせることを推奨。  
ローカルを変更してしまうと、stateファイルの参照ができなくなる場合がある。  
- dynamodb_tableはstateファイルのロック用。同時実行時にの競合を防止するために使用される。  
#### provider
使用するクラウドプロバイダーを指定。  
例:
```
provider "aws" {
    region = "us-west-2"
}
```
#### resource
管理するインフラストラクチャのリソースを定義。  
例:
```
resource "aws_instance" "example" {
 ... 
 }
 ```
#### variable
再利用可能な値を定義。  
例: 
```
variable "instance_type" { 
    default = "t2.micro"
}
```
#### output
他の構成やユーザーに出力する値を定義。  
例:
```
output "instance_id" { 
    value = aws_instance.example.id
}
```
### 各プロバイダーのリソースを作成
AWS、GCPなどのリソース作成はそれぞれで異なる。  
各プロバイダーのサービスを理解して適切に設定していく必要がある。
その文法はHashiCorp内のサイトに存在しているので、実施に参考にしてほしい。
#### AWS
https://registry.terraform.io/providers/hashicorp/aws/latest/docs
#### GCP
https://registry.terraform.io/providers/hashicorp/google/latest/docs
### まとめ
Terraformは、インフラストラクチャの管理をコード化することで、効率的かつ一貫性のある方法でインフラストラクチャを構築および管理するための強力なツールです。多くのクラウドプロバイダーをサポートしており、宣言的な構成とプランニング機能により、インフラストラクチャの変更を安全に行うことができる。

## 規模による使い分け
TBA  

# 参考
- [YouTube] クライン【KLeIn】[【Terraform 入門】Infrastructure as Codeとは？](https://www.youtube.com/watch?v=Y2vv_I4DZfo)
- [YouTube] クライン【KLeIn】[【入門】Terraformの基礎を90分で解説するチュートリアル](https://www.youtube.com/watch?v=h1MDCp7blmg)
- [YouTube] Amazon Web Services Japan 公式 [I-2 : 「それ、どこに出しても恥ずかしくないTerraformコードになってるか？」](https://www.youtube.com/watch?v=0IQ4IScqQws)
