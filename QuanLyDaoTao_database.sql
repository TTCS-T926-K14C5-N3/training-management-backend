IF DB_ID('QuanLyDaoTao') IS NULL
BEGIN
    CREATE DATABASE QuanLyDaoTao;
END
GO

USE QuanLyDaoTao;
GO

-- 1. Bảng NguoiDung
CREATE TABLE dbo.NguoiDung
(
    NguoiDungId INT IDENTITY(1,1) NOT NULL,
    HoTen NVARCHAR(100) NOT NULL,
    Email VARCHAR(150) NOT NULL,
    SoDienThoai VARCHAR(20) NULL,
    MatKhauHash VARCHAR(255) NOT NULL,
    TrangThai VARCHAR(20) NOT NULL DEFAULT 'HoatDong',
    SoLanDangNhapSai INT NOT NULL DEFAULT 0,
    KhoaDen DATETIME2(0) NULL,
    LyDoKhoa NVARCHAR(500) NULL,
    NgayTao DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    NgayCapNhat DATETIME2(0) NULL,
    CONSTRAINT PK_NguoiDung PRIMARY KEY (NguoiDungId),
    CONSTRAINT UQ_NguoiDung_Email UNIQUE (Email),
    CONSTRAINT CK_NguoiDung_TrangThai
        CHECK (TrangThai IN ('HoatDong', 'BiKhoa')),
    CONSTRAINT CK_NguoiDung_SoLanSai
        CHECK (SoLanDangNhapSai >= 0)
);
GO

-- 2. Bảng VaiTro
CREATE TABLE dbo.VaiTro
(
    VaiTroId INT IDENTITY(1,1) NOT NULL,
    TenVaiTro NVARCHAR(50) NOT NULL,
    MoTa NVARCHAR(255) NULL,

    CONSTRAINT PK_VaiTro PRIMARY KEY (VaiTroId)
);
GO

-- 3. Bảng Quyen
CREATE TABLE dbo.Quyen
(
    QuyenId INT IDENTITY(1,1) NOT NULL,
    MaQuyen VARCHAR(100) NOT NULL,
    TenQuyen NVARCHAR(150) NOT NULL,
    MoTa NVARCHAR(255) NULL,

    CONSTRAINT PK_Quyen PRIMARY KEY (QuyenId),
    CONSTRAINT UQ_Quyen_MaQuyen UNIQUE (MaQuyen)
);
GO

-- 4. Bảng NguoiDung_VaiTro
CREATE TABLE dbo.NguoiDung_VaiTro
(
    NguoiDungId INT NOT NULL,
    VaiTroId INT NOT NULL,
    NgayGan DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),

    CONSTRAINT PK_NguoiDung_VaiTro
        PRIMARY KEY (NguoiDungId, VaiTroId),

    CONSTRAINT FK_NguoiDung_VaiTro_NguoiDung
        FOREIGN KEY (NguoiDungId)
        REFERENCES dbo.NguoiDung(NguoiDungId),

    CONSTRAINT FK_NguoiDung_VaiTro_VaiTro
        FOREIGN KEY (VaiTroId)
        REFERENCES dbo.VaiTro(VaiTroId)
);
GO

-- 5. Bảng VaiTro_Quyen
CREATE TABLE dbo.VaiTro_Quyen
(
    VaiTroId INT NOT NULL,
    QuyenId INT NOT NULL,

    CONSTRAINT PK_VaiTro_Quyen
        PRIMARY KEY (VaiTroId, QuyenId),

    CONSTRAINT FK_VaiTro_Quyen_VaiTro
        FOREIGN KEY (VaiTroId)
        REFERENCES dbo.VaiTro(VaiTroId),

    CONSTRAINT FK_VaiTro_Quyen_Quyen
        FOREIGN KEY (QuyenId)
        REFERENCES dbo.Quyen(QuyenId)
);
GO

-- 6. Bảng PhienDangNhap
CREATE TABLE dbo.PhienDangNhap
(
    PhienId BIGINT IDENTITY(1,1) NOT NULL,
    NguoiDungId INT NOT NULL,
    Token VARCHAR(500) NOT NULL,
    ThoiGianBatDau DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    ThoiGianHetHan DATETIME2(0) NOT NULL,
    ThoiGianDangXuat DATETIME2(0) NULL,
    TrangThai VARCHAR(20) NOT NULL DEFAULT 'DangHoatDong',

    CONSTRAINT PK_PhienDangNhap PRIMARY KEY (PhienId),
    CONSTRAINT UQ_PhienDangNhap_Token UNIQUE (Token),

    CONSTRAINT FK_PhienDangNhap_NguoiDung
        FOREIGN KEY (NguoiDungId)
        REFERENCES dbo.NguoiDung(NguoiDungId),

    CONSTRAINT CK_PhienDangNhap_TrangThai
        CHECK (TrangThai IN ('DangHoatDong', 'DaDangXuat', 'HetHan'))
);
GO

-- 7. Bảng TokenMatKhau
CREATE TABLE dbo.TokenMatKhau
(
    TokenId BIGINT IDENTITY(1,1) NOT NULL,
    NguoiDungId INT NOT NULL,
    Token VARCHAR(500) NOT NULL,
    ThoiGianTao DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    ThoiGianHetHan DATETIME2(0) NOT NULL,
    DaSuDung BIT NOT NULL DEFAULT 0,

    CONSTRAINT PK_TokenMatKhau PRIMARY KEY (TokenId),
    CONSTRAINT UQ_TokenMatKhau_Token UNIQUE (Token),

    CONSTRAINT FK_TokenMatKhau_NguoiDung
        FOREIGN KEY (NguoiDungId)
        REFERENCES dbo.NguoiDung(NguoiDungId)
);
GO