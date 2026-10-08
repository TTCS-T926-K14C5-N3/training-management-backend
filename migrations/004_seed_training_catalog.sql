/*
    Starter training programs and subjects for the catalog.
    Run migrations 002_academic_management.sql and 003_training_programs.sql
    before this script. Existing records with the same codes are preserved.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.ChuongTrinhDaoTao', N'U') IS NULL
    THROW 50001, 'Run migration 003_training_programs.sql first.', 1;

IF OBJECT_ID(N'dbo.MonHoc', N'U') IS NULL
    THROW 50002, 'Run migration 002_academic_management.sql first.', 1;

INSERT INTO dbo.ChuongTrinhDaoTao
(
    MaChuongTrinh,
    TenChuongTrinh,
    MoTa,
    TongThoiLuong,
    HocPhiChuan,
    TrangThai
)
SELECT
    sample.MaChuongTrinh,
    sample.TenChuongTrinh,
    sample.MoTa,
    sample.TongThoiLuong,
    sample.HocPhiChuan,
    N'Đang áp dụng'
FROM
(
    VALUES
        (
            N'CNTT-WEB',
            N'Lập trình Web Full-stack',
            N'Kiến thức nền tảng và kỹ năng xây dựng ứng dụng web.',
            240,
            CAST(12000000 AS DECIMAL(12, 2))
        ),
        (
            N'CNTT-PY',
            N'Lập trình Python',
            N'Lập trình Python từ cơ bản đến xây dựng ứng dụng.',
            180,
            CAST(9000000 AS DECIMAL(12, 2))
        ),
        (
            N'CNTT-DATA',
            N'Phân tích dữ liệu',
            N'Xử lý, phân tích và trực quan hóa dữ liệu.',
            200,
            CAST(11000000 AS DECIMAL(12, 2))
        )
) AS sample
(
    MaChuongTrinh,
    TenChuongTrinh,
    MoTa,
    TongThoiLuong,
    HocPhiChuan
)
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.ChuongTrinhDaoTao AS existing
    WHERE existing.MaChuongTrinh = sample.MaChuongTrinh
);

INSERT INTO dbo.MonHoc
(
    MaMonHoc,
    TenMonHoc,
    SoTinChi,
    TrangThai
)
SELECT
    sample.MaMonHoc,
    sample.TenMonHoc,
    sample.SoTinChi,
    N'Đang hoạt động'
FROM
(
    VALUES
        (N'CS101', N'Tin học cơ sở', 3),
        (N'CS102', N'Tư duy lập trình', 3),
        (N'CS201', N'Lập trình Python', 4),
        (N'CS202', N'Cơ sở dữ liệu', 4),
        (N'CS203', N'Cấu trúc dữ liệu và giải thuật', 4),
        (N'WEB201', N'Phát triển giao diện Web', 4),
        (N'WEB202', N'Phát triển Web phía máy chủ', 4),
        (N'DATA201', N'Thống kê ứng dụng', 3),
        (N'DATA202', N'Phân tích và trực quan hóa dữ liệu', 4)
) AS sample(MaMonHoc, TenMonHoc, SoTinChi)
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.MonHoc AS existing
    WHERE existing.MaMonHoc = sample.MaMonHoc
);

COMMIT TRANSACTION;
