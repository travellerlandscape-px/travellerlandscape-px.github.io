# P-X Travel – Shorts-Playbook

## Grundregel (ab 18.11.2026, Entscheidung des Kanalinhabers)
- **Ein Video pro Tag**, nicht mehr.
- **Der Kanalinhaber schneidet selbst** (z. B. CapCut) und legt den fertigen Short in Drive unter `PX-Youtube/fertig` (oder `clips`) ab.
- Er sagt, welches Video hochgeladen wird. Claude lädt **1:1** hoch (Modus `passthrough`), schneidet nichts.
- Claude liefert: Titel, Beschreibung, Hashtags, Tags, Ort, Playlist, KI-Kennzeichnung, Planung, Statistik.

Regeln, nach denen Claude Shorts für den Kanal plant, schneidet und betextet.
Quellen: Hook-Regeln aus `blacktwist/social-media-skills` (hook-writer-sms, MIT) plus eigene Auswertung.

## Erste Sekunden (wichtigster Hebel)
- Der **Bild-Hook** kommt zuerst: stärkste, bewegteste Aufnahme in Sekunde 0 (kein ruhiger Einstieg).
- **Text-Hook auf dem Bild: höchstens 6 Wörter**, groß, gut lesbar, sofort ab 0,2 s.
- Der Text muss eine **Frage aufwerfen, die das Video beantwortet** (Neugier-Lücke), und konkret sein.
- Musik: kein leises Intro, möglichst direkt an einer starken Stelle des Songs einsteigen.

## Hook-Muster (für Reise-Shorts geeignet)
1. **Story-Einstieg:** mitten im Moment, konkret ("A Viking woman was born here").
2. **Zahl/Fakt:** präzise statt rund ("Only 9 people live here").
3. **Kühne Aussage:** "Iceland doesn't look real" – das Video muss es beweisen.
4. **Frage:** spezifisch, nicht generisch ("Would you hike to this?").
5. **Vorher/Nachher bzw. Kontrast:** "Dubai at 6am vs 6pm".
Je Short 5 Varianten erwägen, die stärkste nehmen; Muster im Auftrag notieren, um später zu vergleichen.

## Titel, Beschreibung
- Titel: **Hauptbegriff zuerst** (Ort/Land) + Neugier, Zahl oder Kontrast; nichts versprechen, was das Video nicht hält.
- Shorts folgen den TikTok-Regeln: Hook in 1–3 s entscheidet über Wischen.
- Beschreibung: Ort, 1–2 Sätze Geschichte, Musikquelle, Instagram, Hashtags (Land, Region, Motiv, #shorts).

## Layout
- Kein Text im unteren Drittel (dort liegen Titel/Kanalname) und nicht am rechten Rand (Like-Buttons).
- Ortsnamen klein bei ca. 62–66 % Bildhöhe, Hook/CTA oben.

## Schnitt
- 20–30 s, Schnitte auf den Takt (3–4 Schläge), 0,3 s Übergänge, Zeitlupe nur bei 60-fps-Material.
- Ende so wählen, dass der Loop zum Anfang passt (gleiche Szene/Bewegung) – Wiederholungen zählen als Aufrufe.

## Messen
- Pro Short notieren: Hook-Muster, Länge, Musik. Nach 48 h: Aufrufe, Ø Wiedergabedauer, Wischquote.
- Immer nur eine Sache ändern (z. B. nur den Hook), Muster erst nach 5–10 Shorts bewerten.
- Messwerte: Ø Wiedergabedauer und "angesehen vs. weggewischt" vor reinen Aufrufen.

## Metadaten beim Upload (automatisch)
- Ort: aus den GPS-Daten des ersten Clips mit GPS (oder `location` im Auftrag), Aufnahmedatum aus den Clip-Daten.
- Kategorie: Reisen & Events (19), Sprache Englisch, nicht für Kinder, keine KI-Inhalte.
- Playlists: `playlists` im Auftrag, z. B. ["Iceland"]; fehlende Playlists werden öffentlich angelegt.
- Musik nur aus dem Drive-Ordner `musik` (YouTube Audio Library), Quelle in der Beschreibung nennen.

## Hashtags (Stand 18.11.2026)
- Gesamt 5–8 Hashtags, nie mehr als 15 (manche Quellen: bei Überschreitung ignoriert YouTube alle; offizielle Grenze laut YouTube-Hilfe 60 – unsicher, deshalb konservativ).
- Titel: 1–2 Hashtags am Ende, z. B. `#Iceland #shorts` (`title_hashtags` im Auftrag).
- Beschreibung: die 3 wichtigsten zuerst (erscheinen über dem Titel), z. B. `#iceland #volcano #lava`, danach Region/Motiv; `#shorts` zuletzt.
- Nur passende Hashtags; fremde Trend-Hashtags sind ein Richtlinienverstoß.

## Felder, die die Schnittstelle nicht (sichtbar) setzt
- **Standort** in der App: Koordinaten werden angenommen, aber nicht als Ort angezeigt. Versuch mit `place` (Ortsname). Sonst Ort in Beschreibung und Hashtags, App-Feld bei Bedarf von Hand.
- **Ähnliches Video**: nur in der App möglich.
- **Playlist**: per Schnittstelle, mit Wiederholung; bei Fehler in der App ergänzen.

## KI-Videos (z. B. Seedance-Demos)
- Immer als KI-generiert kennzeichnen (`synthetic: true`), Hinweis auch in der Beschreibung.
- Kategorie Unterhaltung (24), Playlist "AI Videos", kein Ort.
- 1:1 hochladen (Modus `passthrough`): Hochformat unverändert, Querformat nur mittig auf 9:16 zuschneiden, Originalton bleibt.
- Tool-Namen (z. B. Seedance 2.0) in Titel, Tags und Hashtags – danach wird gesucht.
- Höchstens 1 Upload pro Tag; weitere per `publish_at` planen.

## Zielgruppe (Studio-App, Stand 19.11.2026, 28 Tage, ca. 550 Zuschauer)
- 53 % USA, Rest verstreut → Englisch bleibt richtig.
- Alter: 25–34 30 %, 35–44 28 %, 45–54 14 %, 55–64 15 %, 65+ 14 %, unter 25: 0 % → ruhige, informative Reise-Storys statt Jugend-Trends.
- 63 % männlich, 37 % weiblich; 84 % Handy.
- 99,8 % neue Zuschauer, praktisch keine Wiederkehrer → Serienformat und feste Uhrzeit, um Stammzuschauer aufzubauen.
- Veröffentlichungszeit: US-Nachmittag/-Abend (ca. 01:00–05:00 Uhr Dubai); per `publish_at` planbar.
