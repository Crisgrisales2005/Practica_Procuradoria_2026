INSERT INTO modulos (entidad, codigo, nombre, tipo, orden) VALUES
    ('pgn', 'esp_01', 'Constitución Política', 'especifico', 1),
    ('pgn', 'esp_02', 'Estatuto de Conciliación (Ley 2220 de 2022)', 'especifico', 2),
    ('pgn', 'esp_03', 'CPACA (Ley 1437 de 2011)', 'especifico', 3),
    ('pgn', 'esp_04', 'Elaboración de documentos de oficina', 'especifico', 4),
    ('pgn', 'esp_05', 'Atención al usuario', 'especifico', 5),
    ('pgn', 'esp_06', 'Archivo y correspondencia (Ley 594 de 2000, TRD, CCD)', 'especifico', 6),
    ('pgn', 'esp_07', 'Bases de datos', 'especifico', 7),
    ('pgn', 'esp_08', 'Área disciplinar (Ley 1952/2019, Ley 2094/2021, Decreto Ley 262/2000)', 'especifico', 8),
    ('pgn', 'com_09', 'Gestión pública y funcionamiento del Estado', 'comun', 9),
    ('pgn', 'com_10', 'Estructura, organización y funciones de la PGN', 'comun', 10),
    ('pgn', 'com_11', 'Herramientas ofimáticas', 'comun', 11),
    ('pgn', 'com_12', 'Sistemas de gestión', 'comun', 12),
    ('pgn', 'com_13', 'Gestión documental', 'comun', 13)
ON CONFLICT (entidad, codigo) DO NOTHING;
