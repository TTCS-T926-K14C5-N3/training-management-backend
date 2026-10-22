/*
    Backward-compatible database sync for the current ORM contract.
    Run this against the live SQL Server instance before login is used in the web app.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.NguoiDung', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.NguoiDung', N'NgaySinh') IS NULL
        ALTER TABLE dbo.NguoiDung ADD NgaySinh DATE NULL;

    IF COL_LENGTH(N'dbo.NguoiDung', N'DiaChi') IS NULL
        ALTER TABLE dbo.NguoiDung ADD DiaChi NVARCHAR(255) NULL;

    IF COL_LENGTH(N'dbo.NguoiDung', N'DaKichHoat') IS NULL
        ALTER TABLE dbo.NguoiDung ADD DaKichHoat BIT NOT NULL CONSTRAINT DF_NguoiDung_DaKichHoat DEFAULT 1;

    IF COL_LENGTH(N'dbo.NguoiDung', N'BatBuocDoiMatKhau') IS NULL
        ALTER TABLE dbo.NguoiDung ADD BatBuocDoiMatKhau BIT NOT NULL CONSTRAINT DF_NguoiDung_BatBuocDoiMatKhau DEFAULT 0;

    IF COL_LENGTH(N'dbo.NguoiDung', N'CanDoiMatKhau') IS NULL
        ALTER TABLE dbo.NguoiDung ADD CanDoiMatKhau BIT NOT NULL CONSTRAINT DF_NguoiDung_CanDoiMatKhau DEFAULT 0;

    IF COL_LENGTH(N'dbo.NguoiDung', N'MatKhauTamThoiHetHan') IS NULL
        ALTER TABLE dbo.NguoiDung ADD MatKhauTamThoiHetHan DATETIME2(0) NULL;

    IF COL_LENGTH(N'dbo.NguoiDung', N'TokenValidAfter') IS NULL
        ALTER TABLE dbo.NguoiDung ADD TokenValidAfter DATETIME2(0) NULL;
END;

COMMIT TRANSACTION;
