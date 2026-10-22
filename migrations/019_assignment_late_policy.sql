/* Migration 019: Cấu hình chính sách nộp muộn cho bài tập (SCRUM-508) */
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    -- Thêm các cột chính sách nộp muộn vào bảng Assignment nếu chưa có
    IF OBJECT_ID(N'dbo.Assignment', N'U') IS NOT NULL
    BEGIN
        IF COL_LENGTH(N'dbo.Assignment', N'HanNopMuon') IS NULL
            ALTER TABLE dbo.Assignment ADD HanNopMuon DATETIME2 NULL;

        IF COL_LENGTH(N'dbo.Assignment', N'LoaiPhatNopMuon') IS NULL
            ALTER TABLE dbo.Assignment ADD LoaiPhatNopMuon VARCHAR(30) NOT NULL CONSTRAINT DF_Assignment_LoaiPhat DEFAULT 'none';

        IF COL_LENGTH(N'dbo.Assignment', N'GiaTriPhat') IS NULL
            ALTER TABLE dbo.Assignment ADD GiaTriPhat DECIMAL(7,2) NOT NULL CONSTRAINT DF_Assignment_GiaTriPhat DEFAULT 0;

        IF COL_LENGTH(N'dbo.Assignment', N'DiemSanToiThieu') IS NULL
            ALTER TABLE dbo.Assignment ADD DiemSanToiThieu DECIMAL(7,2) NOT NULL CONSTRAINT DF_Assignment_DiemSan DEFAULT 0;
    END;

    -- Thêm các cột lưu chi tiết điểm trước phạt và điểm trừ nộp muộn vào AssignmentGrade
    IF OBJECT_ID(N'dbo.AssignmentGrade', N'U') IS NOT NULL
    BEGIN
        IF COL_LENGTH(N'dbo.AssignmentGrade', N'DiemGoc') IS NULL
            ALTER TABLE dbo.AssignmentGrade ADD DiemGoc DECIMAL(7,2) NULL;

        IF COL_LENGTH(N'dbo.AssignmentGrade', N'DiemTruPhat') IS NULL
            ALTER TABLE dbo.AssignmentGrade ADD DiemTruPhat DECIMAL(7,2) NOT NULL CONSTRAINT DF_AssignmentGrade_DiemTru DEFAULT 0;
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
