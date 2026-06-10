# GUI Review — alla 13 UR10-templates (2026-06-07)

Faithful cup-config aktiv: asset-gripper + NVIDIA out-the-end-kopp, `_ca_deg=0`, descend-repoint `-90`.
Läge: **FEEDBACK-INSAMLING** (ingen analys/fix förrän alla 13 är genomgångna).

Gate-status innan reviewen (headless, default seeds om ej annat): **9/13**.

| # | Template | Gate | Pick (xy,z) | Anton-feedback |
|---|----------|------|-------------|----------------|
| 1 | CP-69 | ✓ | [-1.0, 0.4, 0.835] | Kör IGENOM kuben (ingen kollision/fysik), upp till pick, plockar, åker till bin men SLÄPPER EJ → snurrar ett helt varv → tillbaka till bin → släpper efter några sek |
| 2 | CP-70 | ✓ | [-0.5, 0.4, 0.835] | EXAKT samma som CP-69 (pass-through genom kub, sen release, extra helt varv) |
| 3 | CP-71 | ✗ | dispenser Item_1..4 z≈1.05-1.10 | Isaac Sim verkar HÄNGA — ingen robotaktivitet alls. Scen-bygge: 4 kuber spawnar i LUFTEN ovanför en plattform → faller ner; dessutom en ANNAN svävande platta ovanför |
| 4 | CP-73 | ✗ (timeout) | Cube_1..4 x=-1.6..-1.0 | Samma som CP-69/70 (igenom kub→pick→bin, släpper ej, extra varv, sen release). Inget händer efter kub 1, ingen conveyor-rörelse |
| 5 | CP-75 | ✓ | | |
| 6 | CP-79 | ✓ | | |
| 7 | CP-80 | ✓ | | |
| 8 | CP-81 | ✓ (kräver IKSEEDS=64) | | |
| 9 | CP-82 | ✗ | | |
| 10 | CP-83 | ✗ (kant, kubtopp 0.95) | | |
| 11 | CP-84 | ✓ | | |
| 12 | CP-85 | ✓ | | |
| 13 | CP-86 | ✓ | | |

## ARBETSDIREKTIV (Anton, 2026-06-07) — feedback klar, nu fixa

Anton avslutade feedback efter CP-73 (mönstret upprepas). Beordrad agent-wave (ultracode) för att lösa.

**Detektor som behövs:** se att suction-koppen är (a) i KONTAKT med robotarmen (inget gap), (b) CENTRERAD, (c) INTE 90°-roterad (90°-biten är RÄTT nu). Analysera tidsseriedata så jag kan SE det Anton ser med ögonen.

**Fix-ordning (Antons prioritet):**
1. **Avståndet/gapet robotarm ↔ suction cup** (G2 — det vi höll på med igår, oklart varför ej löst)
2. **Pass-through** — koppen går igenom kuben utan kollision
3. **Planeringen** — släpper inte vid bin, tar ett extra helt varv innan release

Kit-RPC är single-tenant → agent-wave gör READ-ONLY kodanalys (ingen Kit-åtkomst); all Kit-observation/verifiering körs SERIELLT av mig. Gated fixes, bevara passers, verifiera på FRESH Kit.

## GENERELLA observationer (gäller över templates, ej template-specifika)

- **G1 — Vilopose före Play:** roboten **ligger på bordet** (kollapsad/fel authored pose) och **grippern står i 90°** innan man trycker Play. (Den raka koppen + nedåt-repoint verkar bara ske vid exekvering, inte i authored pose. Kopplar ev. till wound-start-assetet.)
- **G2 — Suction-gap kvarstår:** även när scenen spelas finns **fortfarande ett gap mellan suction-koppen och leden ovanför** — den elongation/mount-glapp vi tjatat om hur länge som helst. INTE löst.

## Detaljerad feedback

### CP-69
- Armen åker NER mot kuben men passerar **rakt igenom den som om den vore transparent** — ingen kollision/fysik. Borde stöta till kuben.
- Efter att ha gått igenom kuben åker den UPP till pick-positionen.
- Plockar upp kuben, åker till bin — men **släpper inte** kuben.
- **Snurrar ett helt varv** runt.
- Åker tillbaka till bin, och **släpper kuben först efter några sekunder**.
- Hypoteser att kolla i tidsserie senare: (a) pass-through = kub-collider av/penetration under descend; (b) sen release + extra varv = release-timing/place-segment + onödig wrist-rotation. (EJ åtgärdat — feedback-läge.)

