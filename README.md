# Mercusys Halo

Integracja Home Assistant dla lokalnego panelu Mercusys Halo (m.in. H50G).

Adres panelu, hasło i lista jednostek pochodzą z konfiguracji oraz z samego routera.

## Co jest w Home Assistant

- przełącznik całego Wi-Fi
- restart każdej jednostki Halo oraz restart wszystkich
- sprawdzenie aktualizacji firmware (bez wgrywania)
- stan internetu i połączenia każdej jednostki
- odczyt pasm radiowych i sieci gości
- adres WAN, adres LAN i liczba klientów
- obecność urządzeń z listy klientów

Panel przyjmuje jedną sesję administratora. Odświeżanie wylogowuje przeglądarkę z panelu.

## Instalacja przez HACS

1. HACS → trzy kropki → **Custom repositories**.
2. Wklej adres tego repozytorium.
3. Kategoria: **Integration**.
4. Pobierz **Mercusys Halo**.
5. Zrestartuj Home Assistant.
6. Ustawienia → Urządzenia i usługi → Dodaj integrację → **Mercusys Halo**.
7. Podaj adres głównego Halo i hasło właściciela z aplikacji Mercusys. Sprawdzanie certyfikatu SSL zostaw wyłączone, dopóki panel ma własny certyfikat.

Odświeżanie domyślnie co 60 sekund. Interwał jest w opcjach integracji.
