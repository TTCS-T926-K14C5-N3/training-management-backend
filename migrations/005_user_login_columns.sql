/* Add account and profile columns required by the current user model. */

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.NguoiDung', N'U') IS NULL
    THROW 50001, 'dbo.NguoiDung table does not exist.', 1;

IF COL_LENGTH(N'dbo.NguoiDung', N'NgaySinh') IS NULL
    ALTER TABLE dbo.NguoiDung ADD NgaySinh DATE NULL;

IF COL_LENGTH(N'dbo.NguoiDung', N'DiaChi') IS NULL
    ALTER TABLE dbo.NguoiDung ADD DiaChi NVARCHAR(255) NULL;

IF COL_LENGTH(N'dbo.NguoiDung', N'BatBuocDoiMatKhau') IS NULL
    ALTER TABLE dbo.NguoiDung
        ADD BatBuocDoiMatKhau BIT NOT NULL
            CONSTRAINT DF_NguoiDung_BatBuocDoiMatKhau DEFAULT (0) WITH VALUES;

IF COL_LENGTH(N'dbo.NguoiDung', N'CanDoiMatKhau') IS NULL
    ALTER TABLE dbo.NguoiDung
        ADD CanDoiMatKhau BIT NOT NULL
            CONSTRAINT DF_NguoiDung_CanDoiMatKhau DEFAULT (0) WITH VALUES;

IF COL_LENGTH(N'dbo.NguoiDung', N'MatKhauTamThoiHetHan') IS NULL
    ALTER TABLE dbo.NguoiDung ADD MatKhauTamThoiHetHan DATETIME2 NULL;

COMMIT TRANSACTION;