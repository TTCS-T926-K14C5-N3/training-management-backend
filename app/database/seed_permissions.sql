-- =========================================
-- Seed permissions
-- =========================================

IF NOT EXISTS (
    SELECT 1 FROM Quyen WHERE MaQuyen = 'USER_VIEW'
)
INSERT INTO Quyen (MaQuyen, TenQuyen)
VALUES ('USER_VIEW', N'Xem người dùng');

IF NOT EXISTS (
    SELECT 1 FROM Quyen WHERE MaQuyen = 'USER_CREATE'
)
INSERT INTO Quyen (MaQuyen, TenQuyen)
VALUES ('USER_CREATE', N'Tạo người dùng');

IF NOT EXISTS (
    SELECT 1 FROM Quyen WHERE MaQuyen = 'USER_UPDATE'
)
INSERT INTO Quyen (MaQuyen, TenQuyen)
VALUES ('USER_UPDATE', N'Cập nhật người dùng');

IF NOT EXISTS (
    SELECT 1 FROM Quyen WHERE MaQuyen = 'USER_LOCK'
)
INSERT INTO Quyen (MaQuyen, TenQuyen)
VALUES ('USER_LOCK', N'Khóa người dùng');

IF NOT EXISTS (
    SELECT 1 FROM Quyen WHERE MaQuyen = 'USER_UNLOCK'
)
INSERT INTO Quyen (MaQuyen, TenQuyen)
VALUES ('USER_UNLOCK', N'Mở khóa người dùng');


-- =========================================
-- Mapping admin -> 5 permissions
-- =========================================

INSERT INTO VaiTro_Quyen (VaiTroId, QuyenId)
SELECT 1, q.QuyenId
FROM Quyen q
WHERE q.MaQuyen IN (
    'USER_VIEW',
    'USER_CREATE',
    'USER_UPDATE',
    'USER_LOCK',
    'USER_UNLOCK'
)
AND NOT EXISTS (
    SELECT 1
    FROM VaiTro_Quyen vtq
    WHERE vtq.VaiTroId = 1
      AND vtq.QuyenId = q.QuyenId
);


-- =========================================
-- Mapping user -> USER_VIEW
-- =========================================

INSERT INTO VaiTro_Quyen (VaiTroId, QuyenId)
SELECT 2, q.QuyenId
FROM Quyen q
WHERE q.MaQuyen = 'USER_VIEW'
AND NOT EXISTS (
    SELECT 1
    FROM VaiTro_Quyen vtq
    WHERE vtq.VaiTroId = 2
      AND vtq.QuyenId = q.QuyenId
);