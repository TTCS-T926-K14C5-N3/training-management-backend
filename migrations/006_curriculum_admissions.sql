/*
    Apply the final subject coefficient constraint for curriculum admissions.
    Run after migrations/005_curriculum_admissions.sql.
    Idempotent. Validates the table, column, and existing data before changing
    the constraint so a failed deployment does not remove the current rule.
*/
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.MonHoc', N'U') IS NULL
    THROW 50001, 'Table dbo.MonHoc does not exist. Apply academic migrations first.', 1;

IF COL_LENGTH(N'dbo.MonHoc', N'TrongSo') IS NULL
    THROW 50002, 'Column dbo.MonHoc.TrongSo does not exist. Apply migration 005 first.', 1;

DECLARE @HasInvalidValues BIT = 0;
EXEC sys.sp_executesql
    N'IF EXISTS
      (
          SELECT 1
          FROM dbo.MonHoc
          WHERE TrongSo < 0 OR TrongSo > 1
      )
          SET @HasInvalidValues = 1;',
    N'@HasInvalidValues BIT OUTPUT',
    @HasInvalidValues = @HasInvalidValues OUTPUT;

IF @HasInvalidValues = 1
    THROW 50003, 'Cannot apply the constraint: dbo.MonHoc contains TrongSo values outside [0, 1]. Correct the data and rerun.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    IF EXISTS
    (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.MonHoc')
          AND name = N'CK_MonHoc_TrongSo'
    )
        ALTER TABLE dbo.MonHoc DROP CONSTRAINT CK_MonHoc_TrongSo;

    EXEC sys.sp_executesql
        N'ALTER TABLE dbo.MonHoc
          ADD CONSTRAINT CK_MonHoc_TrongSo
          CHECK (TrongSo >= 0 AND TrongSo <= 1);';

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
