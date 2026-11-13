-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
-- Profile oczekiwań nie są rachunkami i nie generują należności.
CREATE TABLE profile_rachunkow (
    id INTEGER PRIMARY KEY,
    nazwa TEXT NOT NULL CHECK(length(trim(nazwa)) > 0),
    dostawca TEXT NOT NULL DEFAULT '',
    kategoria_id INTEGER REFERENCES kategorie(id) ON DELETE RESTRICT,
    aktywny INTEGER NOT NULL DEFAULT 1 CHECK(aktywny IN (0,1)),
    utworzono_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE harmonogramy_rachunkow (
    id INTEGER PRIMARY KEY,
    profil_id INTEGER NOT NULL REFERENCES profile_rachunkow(id) ON DELETE RESTRICT,
    wersja INTEGER NOT NULL CHECK(wersja >= 1),
    cykl_od TEXT NOT NULL CHECK(length(cykl_od)=7),
    cykl_do TEXT CHECK(cykl_do IS NULL OR length(cykl_do)=7),
    typ TEXT NOT NULL CHECK(typ IN ('miesieczny','co_n_miesiecy','nieregularny')),
    co_ile_miesiecy INTEGER NOT NULL DEFAULT 1 CHECK(co_ile_miesiecy BETWEEN 1 AND 120),
    cykl_kotwicy TEXT NOT NULL CHECK(length(cykl_kotwicy)=7),
    przesuniecie_dni INTEGER NOT NULL DEFAULT 0 CHECK(przesuniecie_dni BETWEEN -62 AND 180),
    utworzono_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(profil_id, wersja),
    UNIQUE(profil_id, cykl_od),
    CHECK(cykl_do IS NULL OR cykl_do >= cykl_od)
);
CREATE INDEX idx_harmonogramy_profil_cykl ON harmonogramy_rachunkow(profil_id,cykl_od,cykl_do);

CREATE TABLE oczekiwane_dokumenty (
    id INTEGER PRIMARY KEY,
    profil_id INTEGER NOT NULL REFERENCES profile_rachunkow(id) ON DELETE RESTRICT,
    harmonogram_id INTEGER NOT NULL REFERENCES harmonogramy_rachunkow(id) ON DELETE RESTRICT,
    cykl TEXT NOT NULL CHECK(length(cykl)=7),
    oczekiwany_od TEXT NOT NULL CHECK(length(oczekiwany_od)=10),
    wyjatek TEXT CHECK(wyjatek IS NULL OR wyjatek IN ('nie_wystawiono','niepewne')),
    powod_wyjatku TEXT,
    UNIQUE(profil_id, cykl)
);
CREATE INDEX idx_oczekiwane_cykl ON oczekiwane_dokumenty(cykl,oczekiwany_od);

CREATE TABLE powiazania_oczekiwanych (
    oczekiwany_id INTEGER NOT NULL REFERENCES oczekiwane_dokumenty(id) ON DELETE CASCADE,
    rachunek_id INTEGER NOT NULL REFERENCES rachunki(id) ON DELETE RESTRICT,
    utworzono_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY(oczekiwany_id,rachunek_id)
);
CREATE INDEX idx_powiazania_rachunek ON powiazania_oczekiwanych(rachunek_id);
