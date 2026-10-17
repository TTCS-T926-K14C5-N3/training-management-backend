IF OBJECT_ID(N'dbo.ThoiKhoaBieu', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ThoiKhoaBieu (
        ThoiKhoaBieuId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ThoiKhoaBieu PRIMARY KEY,
        LopHocId INT NOT NULL,
        MonHocId INT NOT NULL,
        GiangVienId INT NOT NULL,
        PhongHocId INT NOT NULL,
        NgayHoc DATE NOT NULL,
        GioBatDau TIME(0) NOT NULL,
        GioKetThuc TIME(0) NOT NULL,
        TrangThai NVARCHAR(20) NOT NULL
            CONSTRAINT DF_ThoiKhoaBieu_TrangThai DEFAULT N'Lên lịch',
        BaiHocId INT NULL,
        NoiDungBaiHoc NVARCHAR(1000) NULL,
        LyDoHuy NVARCHAR(1000) NULL,
        NgayHuy DATETIME2(0) NULL,
        NguoiHuyId INT NULL,
        NgayTao DATETIME2(0) NOT NULL
            CONSTRAINT DF_ThoiKhoaBieu_NgayTao DEFAULT SYSUTCDATETIME(),
        NguoiTaoId INT NULL,
        NgayCapNhat DATETIME2(0) NOT NULL
            CONSTRAINT DF_ThoiKhoaBieu_NgayCapNhat DEFAULT SYSUTCDATETIME(),
        NguoiCapNhatId INT NULL,
        CONSTRAINT CK_ThoiKhoaBieu_Gio CHECK (GioKetThuc > GioBatDau),
        CONSTRAINT CK_ThoiKhoaBieu_TrangThai
            CHECK (TrangThai IN (N'Lên lịch', N'Đã hủy', N'Hoàn thành')),
        CONSTRAINT FK_ThoiKhoaBieu_LopHoc
            FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
        CONSTRAINT FK_ThoiKhoaBieu_MonHoc
            FOREIGN KEY (MonHocId) REFERENCES dbo.MonHoc(MonHocId),
        CONSTRAINT FK_ThoiKhoaBieu_GiangVien
            FOREIGN KEY (GiangVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
        CONSTRAINT FK_ThoiKhoaBieu_PhongHoc
            FOREIGN KEY (PhongHocId) REFERENCES dbo.PhongHoc(PhongHocId),
        CONSTRAINT FK_ThoiKhoaBieu_NguoiHuy
            FOREIGN KEY (NguoiHuyId) REFERENCES dbo.NguoiDung(NguoiDungId),
        CONSTRAINT FK_ThoiKhoaBieu_NguoiTao
            FOREIGN KEY (NguoiTaoId) REFERENCES dbo.NguoiDung(NguoiDungId),
        CONSTRAINT FK_ThoiKhoaBieu_NguoiCapNhat
            FOREIGN KEY (NguoiCapNhatId) REFERENCES dbo.NguoiDung(NguoiDungId)
    );

    CREATE INDEX IX_ThoiKhoaBieu_Lich
        ON dbo.ThoiKhoaBieu(NgayHoc, GioBatDau, GioKetThuc, TrangThai);
    CREATE INDEX IX_ThoiKhoaBieu_LopHoc
        ON dbo.ThoiKhoaBieu(LopHocId, MonHocId);
END;
GO

IF OBJECT_ID(N'dbo.ThoiKhoaBieu_LichSu', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ThoiKhoaBieu_LichSu (
        ThoiKhoaBieuLichSuId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ThoiKhoaBieu_LichSu PRIMARY KEY,
        ThoiKhoaBieuId INT NOT NULL,
        HanhDong NVARCHAR(20) NOT NULL,
        DuLieuCu NVARCHAR(MAX) NULL,
        DuLieuMoi NVARCHAR(MAX) NULL,
        LyDo NVARCHAR(1000) NULL,
        ThoiDiem DATETIME2(0) NOT NULL
            CONSTRAINT DF_ThoiKhoaBieu_LichSu_ThoiDiem DEFAULT SYSUTCDATETIME(),
        NguoiThucHienId INT NOT NULL,
        CONSTRAINT FK_ThoiKhoaBieu_LichSu_BuoiHoc
            FOREIGN KEY (ThoiKhoaBieuId)
            REFERENCES dbo.ThoiKhoaBieu(ThoiKhoaBieuId),
        CONSTRAINT FK_ThoiKhoaBieu_LichSu_NguoiThucHien
            FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
    );

    CREATE INDEX IX_ThoiKhoaBieu_LichSu_BuoiHoc
        ON dbo.ThoiKhoaBieu_LichSu(ThoiKhoaBieuId, ThoiDiem);
END;
GO

IF OBJECT_ID(N'dbo.ThoiKhoaBieu_DiemDanh', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ThoiKhoaBieu_DiemDanh (
        ThoiKhoaBieuDiemDanhId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ThoiKhoaBieu_DiemDanh PRIMARY KEY,
        ThoiKhoaBieuId INT NOT NULL,
        HocVienId INT NOT NULL,
        TrangThai NVARCHAR(20) NOT NULL,
        GhiChu NVARCHAR(MAX) NULL,
        NguoiDiemDanhId INT NOT NULL,
        NgayCapNhat DATETIME2(0) NOT NULL
            CONSTRAINT DF_ThoiKhoaBieu_DiemDanh_NgayCapNhat
            DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_ThoiKhoaBieu_DiemDanh_BuoiHoc_HocVien
            UNIQUE (ThoiKhoaBieuId, HocVienId),
        CONSTRAINT FK_ThoiKhoaBieu_DiemDanh_BuoiHoc
            FOREIGN KEY (ThoiKhoaBieuId)
            REFERENCES dbo.ThoiKhoaBieu(ThoiKhoaBieuId),
        CONSTRAINT FK_ThoiKhoaBieu_DiemDanh_HocVien
            FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
        CONSTRAINT FK_ThoiKhoaBieu_DiemDanh_NguoiDiemDanh
            FOREIGN KEY (NguoiDiemDanhId) REFERENCES dbo.NguoiDung(NguoiDungId)
    );
END;
GO
