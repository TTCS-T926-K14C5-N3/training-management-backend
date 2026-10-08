/*
    Training program catalog and optional class association.
    Run once against the configured SQL Server database.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.ChuongTrinhDaoTao', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChuongTrinhDaoTao
    (
        ChuongTrinhId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ChuongTrinhDaoTao PRIMARY KEY,
        MaChuongTrinh NVARCHAR(30) NOT NULL,
        TenChuongTrinh NVARCHAR(150) NOT NULL,
        MoTa NVARCHAR(1000) NULL,
        TongThoiLuong INT NOT NULL,
        HocPhiChuan DECIMAL(12,2) NOT NULL,
        TrangThai NVARCHAR(30) NOT NULL
            CONSTRAINT DF_ChuongTrinhDaoTao_TrangThai
            DEFAULT N'Đang áp dụng',
        NgayTao DATETIME2 NOT NULL
            CONSTRAINT DF_ChuongTrinhDaoTao_NgayTao
            DEFAULT SYSUTCDATETIME(),
        NgayCapNhat DATETIME2 NULL,
        CONSTRAINT UQ_ChuongTrinhDaoTao_Ma
            UNIQUE (MaChuongTrinh),
        CONSTRAINT CK_ChuongTrinhDaoTao_TongThoiLuong
            CHECK (TongThoiLuong > 0),
        CONSTRAINT CK_ChuongTrinhDaoTao_HocPhiChuan
            CHECK (HocPhiChuan >= 0),
        CONSTRAINT CK_ChuongTrinhDaoTao_TrangThai
            CHECK (TrangThai IN (N'Đang áp dụng', N'Ngừng áp dụng'))
    );
END;

IF COL_LENGTH(N'dbo.LopHoc', N'ChuongTrinhId') IS NULL
BEGIN
    ALTER TABLE dbo.LopHoc
        ADD ChuongTrinhId INT NULL;

    ALTER TABLE dbo.LopHoc
        ADD CONSTRAINT FK_LopHoc_ChuongTrinhDaoTao
        FOREIGN KEY (ChuongTrinhId)
        REFERENCES dbo.ChuongTrinhDaoTao(ChuongTrinhId);

    CREATE INDEX IX_LopHoc_ChuongTrinhId
        ON dbo.LopHoc(ChuongTrinhId, TrangThai);
END;

IF EXISTS
(
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.LopHoc')
      AND name = N'TenLop'
      AND max_length < 300
)
    ALTER TABLE dbo.LopHoc ALTER COLUMN TenLop NVARCHAR(150) NOT NULL;

COMMIT TRANSACTION;
