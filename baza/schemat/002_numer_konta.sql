-- SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
-- Numer konta bankowego jest oddzielny od numeru faktury.
-- Migracji 001 nie wolno modyfikować: istniejące dane zostają zachowane.
ALTER TABLE rachunki ADD COLUMN numer_konta TEXT NOT NULL DEFAULT '';
