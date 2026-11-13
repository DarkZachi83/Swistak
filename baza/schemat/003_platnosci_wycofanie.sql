-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
-- AI Core etap 3: płatności, logiczne wycofywanie, rewizja faktur.
-- Historycznych migracji 001/002 nie zmieniamy.
ALTER TABLE rachunki ADD COLUMN data_oplacenia TEXT;
ALTER TABLE rachunki ADD COLUMN wycofano_utc TEXT;
ALTER TABLE rachunki ADD COLUMN powod_wycofania TEXT;
ALTER TABLE rachunki ADD COLUMN wersja_rekordu INTEGER NOT NULL DEFAULT 1 CHECK(wersja_rekordu >= 1);

CREATE INDEX idx_rachunki_aktywne_termin ON rachunki(wycofano_utc, status, termin_platnosci);
CREATE INDEX idx_rachunki_okres ON rachunki(okres_do, data_wystawienia);
