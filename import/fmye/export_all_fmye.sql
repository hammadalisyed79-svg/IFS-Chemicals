-- =============================================================================
-- FMYE11 (SQL Anywhere 11) — export ALL tables to CSV
-- Run in: Sybase Central -> Tools -> SQL Anywhere 11 -> Interactive SQL (dbisql)
-- Connect to database FMYE11 first.
--
-- BEFORE RUNNING:
--   1. Create folder:  C:\FMYE_EXPORT\csv\
--   2. In dbisql: Database -> Connect -> FMYE11
--   3. Run STEP 1 below to see all table names
--   4. Run STEP 2 (one UNLOAD per table) OR use dbunload (see EXPORT_FROM_FMYE.txt)
-- =============================================================================

-- STEP 1 — List every user table (copy names from result)
SELECT u.user_name AS schema_name,
       t.table_name
  FROM SYS.SYSTABLE t
  JOIN SYS.SYSUSER u ON t.creator = u.user_id
 WHERE t.table_type = 'BASE'
   AND u.user_name NOT IN ('SYS', 'dbo', 'rs_sys', 'SA_DEBUG')
 ORDER BY u.user_name, t.table_name;

-- STEP 2 — Example: export Voucher table (adjust path and table name)
-- Table names with spaces MUST be quoted.
-- UNLOAD SELECT * FROM DBA."Voucher (salter)"
--   TO 'C:\\FMYE_EXPORT\\csv\\Voucher_salter.csv'
--   FORMAT TEXT QUOTES ON WITH COLUMN NAMES;

-- STEP 3 — Generate UNLOAD statements for ALL DBA tables (run result, then run each line)
SELECT 'UNLOAD SELECT * FROM DBA."' || t.table_name || '" TO ''C:\\FMYE_EXPORT\\csv\\' ||
       REPLACE(t.table_name, ' ', '_') || '.csv'' FORMAT TEXT QUOTES ON WITH COLUMN NAMES;'
  FROM SYS.SYSTABLE t
  JOIN SYS.SYSUSER u ON t.creator = u.user_id
 WHERE t.table_type = 'BASE'
   AND u.user_name = 'DBA'
 ORDER BY t.table_name;

-- STEP 4 — Optional: export only 2023–2026 vouchers
-- UNLOAD
--   SELECT *
--     FROM DBA."Voucher (salter)"
--    WHERE YEAR(VoucherDate) BETWEEN 2023 AND 2026
--   TO 'C:\\FMYE_EXPORT\\csv\\Voucher_salter_2023_2026.csv'
--   FORMAT TEXT QUOTES ON WITH COLUMN NAMES;
