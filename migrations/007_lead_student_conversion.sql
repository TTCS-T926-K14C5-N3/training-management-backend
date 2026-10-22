/*
    Persist lead-to-student conversions, generated student codes, and the
    terminal "Đã nhập học" lead status. Safe to rerun.
*/
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.TuyenSinh_Lead', N'U') IS NULL
    THROW 50001, 'Table dbo.TuyenSinh_Lead does not exist. Apply admissions migrations first.', 1;
IF OBJECT_ID(N'dbo.NguoiDung', N'U') IS NULL
    THROW 50002, 'Table dbo.NguoiDung does not exist. Apply user migrations first.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @EmailMaxLength SMALLINT;
    SELECT @EmailMaxLength = max_length
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.NguoiDung')
      AND name = N'Email';

    IF @EmailMaxLength IS NULL
        THROW 50003, 'Column dbo.NguoiDung.Email does not exist.', 1;

    IF @EmailMaxLength < 255
    BEGIN
        IF EXISTS
        (
            SELECT 1
            FROM sys.key_constraints
            WHERE parent_object_id = OBJECT_ID(N'dbo.NguoiDung')
              AND name = N'UQ_NguoiDung_Email'
        )
            ALTER TABLE dbo.NguoiDung
                DROP CONSTRAINT UQ_NguoiDung_Email;

        ALTER TABLE dbo.NguoiDung
            ALTER COLUMN Email VARCHAR(255) NOT NULL;

        ALTER TABLE dbo.NguoiDung
            ADD CONSTRAINT UQ_NguoiDung_Email UNIQUE (Email);
    END;

    IF EXISTS
    (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead')
          AND name = N'CK_TuyenSinh_Lead_TrangThai'
    )
        ALTER TABLE dbo.TuyenSinh_Lead
            DROP CONSTRAINT CK_TuyenSinh_Lead_TrangThai;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead')
          AND name = N'CK_TuyenSinh_Lead_TrangThai'
    )
        ALTER TABLE dbo.TuyenSinh_Lead
            ADD CONSTRAINT CK_TuyenSinh_Lead_TrangThai
            CHECK
            (
                TrangThai IN
                (
                    N'Mới',
                    N'Đang liên hệ',
                    N'Tiềm năng',
                    N'Đã chuyển đổi',
                    N'Đã nhập học',
                    N'Không tiềm năng'
                )
            );

    IF OBJECT_ID(N'dbo.TuyenSinh_Lead_ChuyenDoi', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.TuyenSinh_Lead_ChuyenDoi
        (
            LeadId INT NOT NULL
                CONSTRAINT PK_TuyenSinh_Lead_ChuyenDoi PRIMARY KEY,
            NguoiDungId INT NOT NULL,
            MaHocVien VARCHAR(20) NOT NULL,
            ChuongTrinhId INT NULL,
            NgayNhapHoc DATETIME2 NOT NULL,
            NguoiChuyenDoiId INT NOT NULL,
            CONSTRAINT UQ_TuyenSinh_Lead_ChuyenDoi_NguoiDung
                UNIQUE (NguoiDungId),
            CONSTRAINT UQ_TuyenSinh_Lead_ChuyenDoi_MaHocVien
                UNIQUE (MaHocVien),
            CONSTRAINT FK_TuyenSinh_Lead_ChuyenDoi_Lead
                FOREIGN KEY (LeadId)
                REFERENCES dbo.TuyenSinh_Lead(LeadId),
            CONSTRAINT FK_TuyenSinh_Lead_ChuyenDoi_NguoiDung
                FOREIGN KEY (NguoiDungId)
                REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_TuyenSinh_Lead_ChuyenDoi_ChuongTrinh
                FOREIGN KEY (ChuongTrinhId)
                REFERENCES dbo.ChuongTrinhDaoTao(ChuongTrinhId),
            CONSTRAINT FK_TuyenSinh_Lead_ChuyenDoi_NguoiChuyenDoi
                FOREIGN KEY (NguoiChuyenDoiId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
