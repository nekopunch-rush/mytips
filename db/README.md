# Oracle DB Tips

Oracle DB で UPDATE したレコードを SELECT のように表示するパターン集。
SQL*Plus 環境で使用することを想定しています。

## 目次

- [MERGE + RETURNING](./oracle-merge-returning.sql)
  - Oracle 12c 以降で利用可能な、UPDATE と SELECT を1つのSQLで完結する方法。
- [PL/SQLブロック](./oracle-merge-returning-plsql.sql)
  - Oracle 12c 未満でも使える、CURSOR + DBMS_OUTPUT を使った代替パターン。

## 補足事項

- **COMMIT**: DMLと同様、COMMIT文を明示的に発行するまで未確定。必要に応じて `COMMIT;` または `ROLLBACK;` を実行する。
- **SQL*Plus表示**: 12c以降のSQL*Plusでは、MERGE + RETURNING句で結果がSELECTのようにテーブル形式で表示される。
- **Oracle 12c未満**: RETURNING句がMERGEで使えない場合、PL/SQLブロック（CURSOR + DBMS_OUTPUT）で代替する必要がある。
