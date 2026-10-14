# Plan: Hausarbeit Process Mining – Domestic & International Declarations

> [!IMPORTANT]
> **Abgabe: 18.10.2026 über Moodle. Umfang laut Assignment Guide: ca. 15 Seiten bei 2 Personen, Abbildungen und Screenshots sind ausdrücklich erwünscht.**
> Rollen: **Eziz = Celonis/PQL** (Dashboards stehen), **Jesco = Python/PM4Py** (eigenes Repo). Dieses Repo dient nur zum Schreiben. Hier entstehen also kein Code und keine Notebooks, nur Text, Abbildungen und Tabellen.

## 1. Abdeckung der Aufgabenstellung

Der Guide verlangt „Pick two out of three … **Compare the results!**“ und stellt 11 Fragen. Jede Frage bekommt einen festen Ort in der Arbeit:

| # | Frage aus dem Assignment | Kapitel | Quelle der Ergebnisse |
|---|---|---|---|
| 1 | Prozessfluss beschreiben und visualisieren (BPMN/Petri-Netz, sinnvolle Abstraktion) | 2 | Celonis-BPMN ✅ + PM4Py-Modell (Jesco) |
| 2 | Dauer der Prozessinstanzen, auffällige Muster | 3.1 | Celonis ✅ |
| 3 | Bottlenecks und Ursachen | 3.2 | Celonis ✅ |
| 4 | Wie viele Anträge werden abgelehnt, mit welchen Gründen? | 3.3 | Celonis ✅ + Jesco |
| 5 | Unerwartetes Verhalten, z. B. fehlende Permits | 3.4 | Celonis ✅ (748 Cases), Jesco gegenprüfen |
| 6 | Muster, die auf Non-Conformance hindeuten | 3.4/3.5 | Celonis ✅ + Alignments (Jesco) |
| 7 | Unterschiede International vs. Domestic | **durchgängig** + 2.3, Fazit | KPI-Tabelle ✅ |
| 8 | Was fehlt für tiefere Einblicke? | 4.1 | Text |
| 9 | Wo könnte ML helfen (überwacht/unüberwacht)? | 4.2 | Text (+ ggf. Prototyp von Jesco) |
| 10 | Sinnvolle KPIs | 4.3 | PQL (Eziz) |
| 11 | Konkrete Verbesserungsempfehlungen | 6 | Text |
| – | Ergebnisse der Tools vergleichen | 5 | beide |

## 2. Verifizierte Basisstatistik (direkt aus den XES-Dateien)

| | Domestic | International |
|---|---|---|
| Cases | 10.500 | 6.449 |
| Events | 56.437 | 72.151 |
| Aktivitäten | 17 | 34 |
| Case-Start 2016 / 2017 / 2018 | – / 2.240 / 8.260 | 3 / 1.494 / 4.952 |
| `org:resource` | nur `STAFF MEMBER`, `SYSTEM` | nur `STAFF MEMBER`, `SYSTEM` |

Damit sind die Lücken „Events:“ und „Aktivitäten:“ in den Notizen gefüllt.

> [!WARNING]
> **Der „Sprung Anfang 2018“ ist mit hoher Wahrscheinlichkeit ein Datenartefakt.** 2018 beginnen fast **4× so viele Cases** wie 2017. Das passt zur BPIC-2020-Beschreibung: 2017 wurden nur zwei Fakultäten erfasst, 2018 die ganze Universität. Der Konformitätsanstieg ab 01/2018 dürfte daher an der veränderten Grundgesamtheit liegen und nicht an einer Prozessänderung. Für Kapitel 3.1/3.5 ist das ein starkes, kritisches Argument.

## 3. Repo-Struktur

```
content/01_einleitung.tex          content/04_erweitert_kpis.tex
content/02_discovery.tex           content/05_toolvergleich.tex
content/03_performance_conf.tex    content/06_fazit.tex
figures/celonis/   figures/python/   (Jesco legt seine Plots hier ab)
```

- Die bisherigen Notizen (KPI-Tabelle, Bottlenecks, Non-Conformance) aus `01_Einleitung.tex` wandern nach `03_performance_conf.tex`.
- `*.xes` in die `.gitignore` aufnehmen (zusammen ~50 MB, im Schreib-Repo nicht nötig).

## 4. Kapitelplan (Ziel ≈ 15 Seiten)

### Kap. 1 – Einleitung (1 S.) · *zuletzt schreiben*
Motivation und Relevanz von Process Mining (van der Aalst 2016), Datensatz BPIC 2020 (Reisekosten der TU Eindhoven, 2017–2018), Ziel: Verbesserungsfeedback zum Prozess, Vorgehen mit Celonis und PM4Py im Vergleich, Überblick über die Kapitel.

### Kap. 2 – Prozessfluss (2–3 S.)
- **2.1 Domestic**: Happy Path (Submit → Admin → Supervisor → Request Payment → Payment Handled), BPMN aus Celonis, 43,98 % der Cases auf dem Happy Path
- **2.2 International**: zusätzlich Permit-Phase und Trip-Events vor dem Deklarationsteil, BPMN aus Celonis
- **2.3 Abstraktion und Vergleich**: Varianten-Abdeckung (100 vs. 756 Varianten), 17 vs. 34 Aktivitäten. Gegenüberstellung mit dem Modell aus dem Inductive Miner (Jesco)

### Kap. 3 – Performance und Konformität (~5 S., Herzstück)
- **3.1 Durchlaufzeiten**: Verteilung, Ø vs. „ohne Extreme“ (86 vs. 75 d), langer Tail bis 743 d, Domestic 9 d vs. International 66 d. Hinweis auf die fehlende Vergleichbarkeit: International beginnt beim Permit
- **3.2 Bottlenecks**: Domestic → Zahlungsphase (3 + 4 AT). International → *End trip → Declaration submitted* (13 AT, 71 %). *Permit → Start trip* ist Vorlaufzeit und kein Engpass
- **3.3 Rejections**: Häufigkeit je Rolle, Rework-Effekt (+d), Anteil nie bezahlter Cases. **Gründe:** Sie stehen nicht im Log. Nur Indizien lassen sich prüfen, z. B. Zusammenhang mit Betrag, Jahr oder Budget-Owner-Beteiligung (in Celonis per Filter vergleichbar)
- **3.4 Unerwartetes Verhalten**: 748 Trips ohne vorheriges Permit (+29 d), DIRECTOR-Eskalation (637, +52 d), doppelte Einreichungen (7 % / 19 %), ggf. Doppelzahlungen
- **3.5 Non-Conformance-Muster**: Rework-Schleifen, späte Einreichung, fehlende Permits. Formulierung: Gegen den Celonis-Happy-Path ist es eine „Abweichung vom häufigsten Pfad“, gegen Jescos normatives Modell eine echte Non-Conformance

### Kap. 4 – Erweiterte Analysen und KPIs (~3 S.)
- **4.1 Fehlende Daten**: keine Ablehnungsgründe; Ressourcen anonymisiert (nur STAFF MEMBER/SYSTEM), also keine Social-Network- oder Workload-Analyse; keine Start-Events, daher nur Warte- statt Bearbeitungszeiten; keine Reisemerkmale (Ziel, Dauer); keine Dokumentation der Organisationsänderung 2018
- **4.2 ML**: überwacht → Vorhersage, ob ein Case abgelehnt wird oder lange dauert (Predictive Process Monitoring). Unüberwacht → Anomalieerkennung, Trace-Clustering
- **4.3 KPIs (dein PQL-Teil)**: 4–6 KPIs mit Definition, PQL und Werten Domestic/International:

| KPI | PQL-Skizze (Tabellennamen anpassen) |
|---|---|
| Median-Durchlaufzeit | `MEDIAN(CALC_THROUGHPUT(CASE_START TO CASE_END, REMAP_TIMESTAMPS("act"."ts", DAYS)))` |
| First-Time-Right-Quote | `1 - AVG(MATCH_ACTIVITIES("act"."concept:name", NODE['Declaration REJECTED by ADMINISTRATION']))` |
| Rework-Quote | `PU_COUNT(cases, "act"."concept:name", "act"."concept:name"='Declaration SUBMITTED by EMPLOYEE') > 1` |
| Permit-Compliance | `PROCESS EQUALS 'Permit FINAL_APPROVED by SUPERVISOR' TO ANY TO 'Start trip'` |
| Einreichungsverzug nach Reise | `CALC_THROUGHPUT(FIRST_OCCURRENCE['End trip'] TO FIRST_OCCURRENCE['Declaration SUBMITTED by EMPLOYEE'], …)` |
| Zahlungsdauer | Final Approved → Payment Handled |

Screenshots der Dashboards gehören direkt in die Kapitel 3 und 4.

### Kap. 5 – Tool-Vergleich (1–2 S.)
Ein gemeinsamer Abschnitt, gestützt auf eine Vergleichstabelle (Bedienung, Exploration, Discovery, Conformance, Reproduzierbarkeit, ML-Erweiterbarkeit, Kosten). Dazu **„Compare the results!“**: Weichen Kennzahlen wie Varianten, Durchlaufzeit oder Konformitätsquote zwischen Celonis und PM4Py voneinander ab, und warum?

### Kap. 6 – Empfehlungen und Fazit (1–2 S.)
1. Frist oder Reminder für die Einreichung nach Reiseende (Hebel: 13 AT)
2. Systemsperre: kein Trip bzw. keine Deklaration ohne genehmigtes Permit
3. Plausibilitätsprüfung vor dem Absenden senkt Admin-Rejections und Rework
4. Zahlungsphase automatisieren oder bündeln
5. Ablehnungsgründe und Ressourcen strukturiert loggen

Danach Zusammenfassung und Limitationen.

## 5. Übergabe-Checkliste an Jesco

Was ihr für den Text aus seinem Python-Repo braucht (Plots als PDF/PNG nach `figures/python/`):
- [ ] Modell aus dem Inductive Miner bzw. eine DFG für beide Logs (→ 2.3)
- [ ] Normatives Modell, Alignment-Fitness und Anteil konformer Cases (→ 3.4/3.5, 5)
- [ ] Regel-Checks: Trip/Deklaration ohne Permit, Doppelzahlungen, Submit vor End trip (→ 3.4)
- [ ] Rejections je Rolle, nie bezahlte Cases (→ 3.3)
- [ ] Optional: ML-Prototyp (→ 4.2)
- [ ] Ein paar Sätze zu seinen Tool-Erfahrungen (→ 5)
- [ ] Link zum Repo bzw. Notebook für den Anhang (der Guide erlaubt die Abgabe von Notebooks)

## 6. Literatur (Ziel ≈ 10 Quellen)

| Thema | Quelle |
|---|---|
| Grundlagen, Relevanz | van der Aalst (2016) ✅ |
| Datensatz | van Dongen (2020) *BPI Challenge 2020*, 4TU.ResearchData |
| BPMN, KPIs | Dumas et al. (2018) *Fundamentals of BPM* |
| Discovery | Leemans et al. (2013) Inductive Miner |
| Conformance | Carmona et al. (2018) *Conformance Checking* |
| Tools | Berti et al. (2019) *PM4Py*; Vogelgesang et al. (2022) *Celonis PQL* |
| ML im PM | Teinemaa et al. (2019) Outcome-oriented PPM; Nolle et al. BINet |

## 7. Zeitplan

| Tag | Eziz (Celonis + Schreiben) | Jesco (Python + Schreiben) |
|---|---|---|
| **Mi 14.10** | Struktur aufteilen, `.bib` befüllen, Dashboard-Screenshots und BPMN als Bilder exportieren | Abstimmung über die Übergabeliste |
| **Do 15.10** | Kap. 2 + 3.1/3.2 schreiben | Discovery, Conformance, Regel-Checks |
| **Fr 16.10** | Kap. 3.3–3.5 + 4.3 (PQL-KPIs) | Plots übergeben, Kap. 4.2 schreiben |
| **Sa 17.10** | Kap. 4.1, 6, Einleitung | Python-Teile in 2.3/3.4 einarbeiten, Entwurf Kap. 5 |
| **So 18.10** | Gemeinsam: Korrekturlesen, Zahlenkonsistenz, Prozessdokumentation (KI) und Aufteilung aktualisieren, Abgabe über Moodle | |

> [!CAUTION]
> In [process-documentation.tex](file:///Users/eziz/Documents/Process%20Mining/hausarbeit/content/process-documentation.tex) und `aufteilung_tabellen.tex` stehen noch Inhalte aus dem **Bundestag-Projekt**. Sie müssen vor der Abgabe ersetzt werden.

## 8. Offene Fragen
1. Wer schreibt welches Kapitel? Der Zeitplan oben ist nur ein Vorschlag.
2. Wollt ihr eine Aufteilungstabelle (wer hat was verfasst) wieder einbinden?
