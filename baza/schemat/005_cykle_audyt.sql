-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
-- Potwierdzenie kompletności i finansowe rozliczenie to odrębne warunki.
CREATE TABLE cykle_rozliczeniowe (
    cykl TEXT PRIMARY KEY CHECK(length(cykl)=7),
    potwierdzono_kompletnosc INTEGER NOT NULL DEFAULT 0 CHECK(potwierdzono_kompletnosc IN (0,1)),
    potwierdzono_utc TEXT,
    brak_rachunkow_potwierdzony INTEGER NOT NULL DEFAULT 0 CHECK(brak_rachunkow_potwierdzony IN (0,1)),
    uniewazniono_utc TEXT,
    powod_uniewaznienia TEXT,
    CHECK(potwierdzono_kompletnosc=0 OR potwierdzono_utc IS NOT NULL)
);

CREATE TABLE dziennik_zdarzen (
    id INTEGER PRIMARY KEY,
    utworzono_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    obiekt_typ TEXT NOT NULL CHECK(obiekt_typ IN ('invoice','profile','cycle','expectation')),
    obiekt_id TEXT NOT NULL,
    operacja TEXT NOT NULL,
    przed_json TEXT,
    po_json TEXT,
    powod TEXT NOT NULL DEFAULT '',
    zrodlo TEXT NOT NULL DEFAULT 'user' CHECK(zrodlo IN ('user','system'))
);
CREATE INDEX idx_dziennik_obiekt ON dziennik_zdarzen(obiekt_typ,obiekt_id,id);
