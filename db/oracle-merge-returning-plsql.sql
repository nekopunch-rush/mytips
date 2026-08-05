-- Oracle 12c 未満でも使える PL/SQLブロックパターン
-- CURSOR + DBMS_OUTPUT を使った代替方法

SET SERVEROUTPUT ON;

DECLARE
    CURSOR c_target IS
        SELECT KEY_F, KEY_S, KEY_T, STATUS, RETRY_LIMIT_DATE
        FROM DB_SAM.TABLE_A
        WHERE STATUS IN ('002', '004', '006', '101', '102')
          AND RETRY_END_DATE IS NULL
          AND RETRY_LIMIT_DATE BETWEEN TO_DATE('2026/07/23 16:00:00', 'YYYY/MM/DD HH24:MI:SS')
                                   AND TO_DATE('2026/07/23 21:00:00', 'YYYY/MM/DD HH24:MI:SS');
BEGIN
    FOR rec IN c_target LOOP
        UPDATE DB_SAM.TABLE_A
        SET RETRY_LIMIT_DATE = rec.RETRY_LIMIT_DATE + 1
        WHERE KEY_F = rec.KEY_F AND KEY_S = rec.KEY_S AND KEY_T = rec.KEY_T;

        -- 更新後の値を出力（DBMS_OUTPUT）
        DBMS_OUTPUT.PUT_LINE(rec.KEY_F || ',' || rec.KEY_S || ',' || rec.KEY_T ||
                             ',' || rec.STATUS || ',' || (rec.RETRY_LIMIT_DATE + 1));
    END LOOP;

    -- COMMIT文を明示的に発行するまで未確定。必要に応じて COMMIT; または ROLLBACK; を実行する。
END;
/
