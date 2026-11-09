-- SPDX-License-Identifier: GPL-3.0-only
-- Etap 1: dokumenty, rachunki, kategorie i pozycje.
CREATE TABLE dokumenty (
    id INTEGER PRIMARY KEY,
    nazwa_zrodlowa TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE CHECK(length(sha256) = 64),
    sciezka_wzgledna TEXT NOT NULL UNIQUE,
    rozmiar_bajtow INTEGER NOT NULL CHECK(rozmiar_bajtow > 0),
    dodano_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE kategorie (
    id INTEGER PRIMARY KEY,
    nazwa TEXT NOT NULL UNIQUE COLLATE NOCASE,
    aktywna INTEGER NOT NULL DEFAULT 1 CHECK(aktywna IN (0, 1))
);

CREATE TABLE rachunki (
    id INTEGER PRIMARY KEY,
    dokument_id INTEGER NOT NULL UNIQUE REFERENCES dokumenty(id) ON DELETE RESTRICT,
    dostawca TEXT NOT NULL,
    numer TEXT NOT NULL DEFAULT '',
    data_wystawienia TEXT,
    termin_platnosci TEXT,
    okres_od TEXT,
    okres_do TEXT,
    kwota_grosze INTEGER NOT NULL CHECK(kwota_grosze >= 0),
    status TEXT NOT NULL DEFAULT 'do_zaplaty'
        CHECK(status IN ('do_zaplaty', 'oplacony')),
    uwagi TEXT NOT NULL DEFAULT '',
    zmieniono_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE pozycje_rachunku (
    id INTEGER PRIMARY KEY,
    rachunek_id INTEGER NOT NULL REFERENCES rachunki(id) ON DELETE CASCADE,
    kategoria_id INTEGER NOT NULL REFERENCES kategorie(id) ON DELETE RESTRICT,
    opis TEXT NOT NULL DEFAULT '',
    kwota_grosze INTEGER NOT NULL CHECK(kwota_grosze >= 0)
);

CREATE INDEX idx_pozycje_rachunek ON pozycje_rachunku(rachunek_id);
CREATE INDEX idx_pozycje_kategoria ON pozycje_rachunku(kategoria_id);

INSERT INTO kategorie(nazwa) VALUES
    ('Energia elektryczna'), ('Gaz'), ('Czynsz'),
    ('Telefon'), ('Fundusz remontowy'), ('Inne');
