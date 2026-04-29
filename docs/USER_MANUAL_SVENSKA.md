# Deal Meals - Användarmanual

Välkommen till Deal Meals! Den här appen hjälper dig att spara pengar på matinköp genom att hitta recept som matchar aktuella erbjudanden hos din livsmedelsbutik.

**Så fungerar det:** Du väljer den butik du veckohandlar i. Appen hämtar deras aktuella erbjudanden och matchar dem mot tusentals recept. Resultatet? En personlig lista med måltidsförslag baserat på vad som faktiskt är på extrapris just nu.

**Viktigt att förstå:** Deal Meals är designat för att användas mot **en butik i taget** — den du normalt veckohandlar i. Det är inte en prisjämförelsetjänst som jämför priser mellan butiker. Välj en stor matvarubutik med brett sortiment (som Willys, ICA Maxi eller Coop) för bäst resultat. Du kan ladda ner erbjudanden från en mindre kvartersbutik också, men räkna då med att urvalet av recept där du faktiskt sparar pengar blir betydligt mindre.

---

## Innehåll

1. [Komma igång](#1-komma-igång)
2. [Startsidan - Veckans måltider](#2-startsidan---veckans-måltider)
3. [Butiker - Hantera dina matbutiker](#3-butiker---hantera-dina-matbutiker)
4. [Recept - Hantera receptkällor](#4-recept---hantera-receptkällor)
5. [Konfiguration](#5-konfiguration)
6. [Tips & Vanliga frågor](#6-tips--vanliga-frågor)

---

## 1. Komma igång

Första gången du öppnar Deal Meals visas ett **Startguide**-kort på startsidan. Den leder dig genom följande steg:

### Steg 1: Lägg till din adress i Origin Validation

Det här är det enda lite tekniska steget, men det är nödvändigt — utan det kommer appen att blockera alla åtgärder som att hämta erbjudanden och recept.

Deal Meals kontrollerar att anrop kommer från en betrodd adress. Som standard är bara `localhost` och `127.0.0.1` tillåtna. Om du besöker appen från en annan dator eller använder ett servernamn (som `docker01` eller `192.168.1.50`) måste du lägga till den adressen.

**Så här gör du:**

1. Öppna filen `.env` i Deal Meals installationsmapp
2. Hitta sektionen `# Origin validation` och raden `ALLOWED_HOSTS=`
3. Lägg till din servers namn eller IP-adress i listan (kommaseparerat, inga mellanslag)

**Exempel:**
```
ALLOWED_HOSTS=localhost,127.0.0.1,docker01,192.168.1.50
```

Om du använder ett domännamn (t.ex. `deal-meals.example.com`), lägg till det också.

4. Efter att du sparat filen, starta om webbcontainern för att ändringen ska börja gälla:
```
docker compose up -d web
```

> **Tips:** Startguiden på startsidan upptäcker automatiskt vilket servernamn du ansluter via och föreslår vad du ska lägga till.

> **Observera:** Ett vanligt `docker compose restart web` laddar **inte** om `.env`-ändringar. Du måste använda `docker compose up -d web` istället.

### Steg 2: Ange din bostadsadress

Gå till **Konfiguration** och scrolla till **Bostadsadress**. Fyll i:
- Gatuadress
- Postnummer (5 siffror)
- Ort

Detta talar om för appen var du bor så att den kan hitta närliggande butiker och relevanta leveransalternativ.

Du kan börja skriva din adress för att få förslag via OpenStreetMap. **Kontrollera alltid postnumret** — OpenStreetMap returnerar ofta fel postnummer för svenska adresser. Om postnumret är fel kommer dina e-handelsval på Butikssidan inte att matcha ditt faktiska leveransområde.

### Steg 3: Aktivera receptkällor

Gå till **Recept**-sidan. Du ser en lista med svenska recept-webbsidor (ICA, Coop, Köket, m.fl.). Klicka på **pilknappen** för att flytta källor från "Inaktiva" till "Aktiva". Aktiva källor används vid generering av måltidsförslag.

Hämta sedan recept från minst en källa (se [Hämta recept](#43-hämta-recept) nedan).

### Steg 4: Lägg till en butik och hämta erbjudanden

Gå till **Butiker**-sidan. Välj en butik (Willys, ICA, Coop, m.fl.), välj platstyp och klicka på **Hämta erbjudanden** (se [Hämta erbjudanden](#32-hämta-erbjudanden-från-en-butik) nedan).

### Steg 5: Se dina förslag

Gå tillbaka till **Startsidan**. Dina personliga receptförslag baserade på aktuella erbjudanden är nu redo!

### Första cache-uppvärmningen

När du har recept och butikserbjudanden behöver Deal Meals en lyckad ombyggnad
av receptmatchningen innan Startsidan kan visa hela den aktuella uppsättningen
förslag. Precis efter första installationen, en recepthämtning eller en
erbjudandehämtning kan Startsidan därför kort visa färre förslag, gamla förslag
eller inga förslag medan matchningscachen byggs om.

Det finns också en liten prestandauppvärmning: den snabbaste optimerade
cachevägen aktiveras efter 3 verifierade cacheuppdateringar i rad utan problem.
Tills dess fungerar appen ändå, men den gör extra säkerhetskontroller och kan
kännas långsammare. Schemaläggning av recept- och erbjudandehämtning gör att
detta kan ske i bakgrunden.

Startguiden försvinner automatiskt när alla steg är klara.

---

## 2. Startsidan - Veckans måltider

Startsidan är där du kommer spendera mest tid. Den har tre huvudvyer, tillgängliga via knapparna högst upp:

### 2.1 Veckans fyndrecept (standardvy)

Det här är huvudfunktionen. Den visar receptförslag organiserade i fyra färgkodade kategorier:

| Kategori | Färg | Innehåll |
|----------|------|----------|
| Kött & Fågel | Röd | Recept med köttbaserade erbjudanden |
| Fisk & Skaldjur | Blå | Recept med fisk- och skaldjurserbjudanden |
| Vegetariskt | Grön | Recept med vegetariska erbjudanden |
| Smarta köp | Gul | Recept där flest ingredienser finns på extrapris |

**Varje receptkort visar:**
- Receptbild
- Receptnamn
- Källwebbplats
- Uppskattad besparing (hur mycket du sparar med aktuella erbjudanden)
- Tillagningstid
- Antal matchande erbjudanden

**Klicka på ett receptkort** för att öppna originalreceptet på källwebbplatsen i en ny flik.

**Klicka på "Visa erbjudanden"** på ett kort för att öppna en detaljerad popup som visar:
- Alla matchade butikserbjudanden med priser och rabatter
- Vilken ingrediens varje erbjudande matchar
- Länkar till produkterna i butikens webbshop
- Fullständig ingredienslista (med en kopieringsknapp för enkel inköpslista)

#### Uppdatera förslag

Klicka på **uppdateringsknappen** (cirkulär pil) bredvid "Veckans fyndrecept" för att bygga om dina förslag. Användbart efter att du hämtat nya butikserbjudanden.

#### Justera kategoribalansen

Klicka på **kugghjulsikonen** bredvid "Veckans fyndrecept" för att gå till Konfiguration där du kan justera hur många recept från varje kategori du vill se.

### 2.2 Sök recept

Klicka på **Sök recept** för att söka bland alla dina nedladdade recept efter namn eller ingrediens.

- Skriv minst 2 tecken och tryck Enter eller klicka på sökknappen
- Resultaten visar receptkort med namn, källa, tillagningstid och antal portioner
- Klicka på ett kort för att öppna receptet på källwebbplatsen

**Filtrera per receptkälla:** Bredvid sökknappen finns en dropdown-meny med alla aktiva receptkällor (t.ex. ICA.se, Mathem.se, Javligtgott.se). Välj en källa och klicka **Sök** för att visa alla recept från den källan — inget sökord behövs. Du kan även kombinera sökord med källfilter för att söka inom en specifik källa. Listan uppdateras dynamiskt: nya skrapare dyker upp automatiskt och inaktiverade försvinner.

**Dölja recept:** Om du ser ett recept du aldrig vill se igen, klicka på **ögonikonen** på kortet för att dölja det. Dolda recept visas inte i förslag eller sökresultat.

**Återställa dolda recept:** I sökvyn, klicka på **"Visa dolda recept"** för att se alla recept du har dolt. Klicka på **"Återställ"** på valfritt recept för att ta tillbaka det.

### 2.3 Vad kan jag laga? (Skafferimatchning)

Har du redan ingredienser hemma? Klicka på **Vad kan jag laga?** och skriv in vad du har (kommaseparerat).

Exempel: `kyckling, ris, vitlök, tomat`

Appen söker igenom alla dina recept och visar:
- **Fullständiga matchningar** - recept där du har alla (eller nästan alla) ingredienser
- **Delmatchningar** - recept där du bara saknar några få saker, med en lista över vad som fattas

Varje resultat visar en **täckningsgrad** - hur stor andel av receptets ingredienser du redan har.

### 2.4 Statuskort

Under huvudknapparna visas två statuskort med en snabb överblick:

- **Senast hämtade erbjudanden** - vilka butiker som har aktiva erbjudanden, antal produkter och när de senast uppdaterades (med en varning om datan är äldre än 9 dagar)
- **Receptkällor** - hur många källor som är aktiva, totalt antal recept och synkstatus

---

## 3. Butiker - Hantera dina matbutiker

Butikssidan låter dig konfigurera vilka matbutiker du vill följa och hämta deras aktuella erbjudanden.

### 3.1 Butikskonfiguration

Varje butikskort visar butikens logotyp, namn och konfigurationsalternativ. De flesta butiker erbjuder två platstyper:

- **E-handel** (lastbilsikon) - Erbjudanden vid hemleverans. Välj din lokala leveransbutik från en dropdown (använder ditt postnummer från Konfiguration).
- **Fysisk butik** (butiksikon) - Erbjudanden i butiken. Sök efter din närmaste butik via namn eller ort.

Välj din föredragna platstyp och välj din specifika butik. Konfigurationen sparas automatiskt.

**Bra att veta:**
- **Leveransavgifter för e-handel** ingår inte i de visade erbjudandepriserna. De flesta butiker tar en separat leveransavgift för hemleveransbeställningar.
- **Medlemspriser** — Många erbjudanden gäller exklusivt för butiksmedlemmar (t.ex. Willys Plus, ICA Stammis, Coop Medlem). Deal Meals förutsätter att du är medlem. Det är gratis att bli medlem hos alla stora svenska livsmedelskedjor.

### 3.2 Hämta erbjudanden från en butik

När en butik är konfigurerad, klicka på den gröna knappen **"Hämta erbjudanden"** för att ladda ner aktuella kampanjer.

**Vad som händer:**
1. Knappen inaktiveras och en förloppsindikator visas
2. Du ser statusmeddelanden som "Hämtar produkter..." och "Sparar 145 produkter..."
3. När det är klart visas en popup med hur många erbjudanden som hittades
4. Förloppsindikatorn försvinner och knappen aktiveras igen

**Viktigt att veta:**
- Bara en butik kan hämtas åt gången. Om du försöker starta en till medan en pågår visas ett meddelande som ber dig vänta.
- Du kan lugnt byta webbläsarflik eller navigera till andra sidor medan hämtningen körs. Om du kommer tillbaka återupptas förloppet.
- Efter hämtning uppdateras dina receptförslag på startsidan automatiskt.

### 3.3 Schemaläggning av butiker

Under butikskorten finns en **Schemaläggning**-sektion där du kan automatisera hämtning av erbjudanden.

**Skapa ett schema:**
1. Välj en butik från dropdown-menyn
2. Välj frekvens: **Dagligen**, **Veckovis** eller **Månadsvis**
3. För veckovis: välj en veckodag
4. För månadsvis: välj en dag i månaden (1-28, inte 29-31 då februari bara har 28 dagar)
5. Välj timme (24-timmarsformat)
6. Klicka på **Spara**

**Schemaöversiktstabellen** visar alla dina aktiva scheman med:
- Butiksnamn och plats
- Schemabeskrivning (t.ex. "Varje måndag kl 06:00")
- Nästa schemalagda körning
- Senast slutförd körning

Klicka på valfri rad i tabellen för att redigera det schemat. För att ta bort ett schema, välj butiken och sätt frekvens till **"Av"**, eller klicka på **ta bort-knappen**.

---

## 4. Recept - Hantera receptkällor

Receptsidan låter dig hantera var dina recept kommer ifrån och hålla dem uppdaterade.

### 4.1 Receptkällor

Källor visas i två kolumner:

- **Aktiva** (grön ram) - Dessa källor används vid generering av dina veckoreceptförslag
- **Inaktiva** (grå ram) - Tillgängliga men inte aktiva just nu

**Varje källkort visar:**
- Källans namn (klickbar länk till webbplatsen)
- Kort beskrivning
- Antal recept i din databas
- Databasstorlek
- När den senast uppdaterades

**Åtgärder:**
- **Pilknapp** - Flytta mellan aktiva och inaktiva
- **Stjärnknapp** - Markera som favorit (stjärnmärkta källor prioriteras i förslag)
- **Papperskorgknapp** (bara inaktiva) - Ta bort alla recept från denna källa

### 4.2 Konfigurera hämtningar

Varje receptkälla har en **kugghjulsknapp** (⚙) bredvid pilknappen. Klicka på den för att ställa in hur många recept som ska hämtas:

- **Full hämtning** — Antal recept vid "Full"-körning. "Hämta alla" = inga begränsningar.
- **Inkrementell hämtning** — Antal recept vid "Inkrementell"-körning. "Alla nya" = alla nya recept sedan senaste hämtningen.

De valda värdena visas direkt i källans beskrivningstext (t.ex. "Recept från coop.se (500 / alla nya)").

### 4.3 Hämta recept

Använd sektionen **Hämta recept** för att ladda ner recept från dina källor.

**Rekommendation:** Ladda gärna ner flera tusen recept, helst från flera olika
källor. Appen kan fungera med ett mindre urval, men med bara några hundra recept
är chansen mycket lägre att veckans butikserbjudanden råkar matcha ett recept
med hög besparing. Testläget med 20 recept är bara till för att kontrollera att
en källa fungerar.

**Kontroller:**
1. **Välj källa** - Välj en specifik källa/receptsida, eller "Alla aktiva källor" för att uppdatera allt
2. **Körläge:**
   - **Inkrementell** (rekommenderat) - Hämtar bara nya recept sedan senaste körningen. Snabbt.
   - **Full** - Laddar om allt. Långsamt men noggrant. Använd om data verkar ofullständig.
   - **Test** - Laddar bara 20 recept utan att spara. Bra för att kontrollera att en källa fungerar.
3. Klicka på **Hämta recept** för att starta

**Under hämtningen:**
- En snurrande ikon visas med källans namn och förlopp (antal recept hittade hittills)
- Du kan **avbryta** när som helst med den röda avbryt-knappen

**Efter slutförd hämtning:**
- En sammanfattning visar nya recept och totalt antal i databasen
- Receptförslagen på startsidan uppdateras

**Tidsuppskattningar** visas under källväljaren med ungefärlig tid för varje läge för den valda källan.

### 4.4 Receptscheman

Precis som butiksscheman kan du automatisera recepthämtning.

Schemasektionen fungerar på samma sätt som på Butikssidan: välj en källa, ställ in frekvens och tid, och spara. Översiktstabellen visar alla receptscheman med senaste körningsresultat.

### 4.5 Mina Recept — Lägg till egna recept via URL

Utöver de inbyggda receptkällorna kan du lägga till enskilda recept från **vilken recept-webbsida som helst** som stöder schema.org/Recipe-standarden (de flesta stora recept-webbsidor gör det).

**Viktigt:** Varje recept måste ha en **unik URL**. Det är det enda som stöds — du kan inte klistra in recepttext eller ladda upp bilder manuellt.

**Så här gör du:**

1. På **Recept**-sidan finns källan **"Mina Recept"** bland dina receptkällor
2. Klicka på **kugghjulsikonen** (⚙) på Mina Recept-kortet
3. I modalen som öppnas, klistra in en recept-URL och klicka **Lägg till**
4. URL:en läggs till med status ⏳ (ej hämtad ännu)
5. **Kör skraparen** (inkrementell eller full) för att hämta receptdata från URL:erna

**Statusar:**
- ⏳ **Väntande** — URL tillagd men inte hämtad ännu
- ✅ **OK** — Receptet hämtades framgångsrikt (receptnamnet visas)
- ❌ **Fel** — Hämtningen misslyckades (försöks igen automatiskt, upp till 5 gånger)
- ⚠️ **Inget recept** — Sidan hittades men innehöll ingen receptdata

**Bra att veta:**
- Den universella skraparen är per definition något begränsad men bör fungera med uppskattningsvis 70–80% av alla recept som har en URL. Om en specifik webbsida inte fungerar beror det på sidans utformning — då krävs tyvärr en egen anpassad skraper för just den webbsidan.
- JavaScript-renderade sidor hanteras automatiskt via webbläsarfallback
- Du kan ta bort en URL via 🗑-knappen i modalen — det tar även bort det hämtade receptet
- Dubbletter avvisas automatiskt (samma URL kan inte läggas till två gånger)

### 4.6 Om körlägen

Under hämtningssektionen finns en förklaring av varje läge:
- **Inkrementell** - Snabbt, hämtar bara nytt innehåll. Bäst för regelbundna uppdateringar.
- **Test** - Snabbtest med 20 recept, inget sparas. Använd för att verifiera att en källa fungerar.
- **Full** - Komplett omhämtning. Använd ibland om du misstänker att data saknas.

---

## 5. Konfiguration

Inställningssidan har flera sektioner för att anpassa din upplevelse.

### 5.1 Utseende

- **Tema** - Växla mellan ljust och mörkt läge
- **Textstorlek** - Justera textstorleken (12-24px) med ett reglage
- **Hög kontrast** - Aktivera för förbättrad läsbarhet (WCAG AAA-kompatibelt)

Ändringar tillämpas omedelbart och sparas mellan sessioner.

### 5.2 Sorteringsmetod

Välj hur recepten ska rankas:

- **Kronor sparade** (standard) — Recept sorteras efter total besparing i kronor. Bra om du vill maximera rabattens absoluta storlek.
- **Procent sparade** — Recept sorteras efter genomsnittlig procentuell rabatt, viktad mot hur stor andel av ingredienserna som har erbjudanden. Bra om du vill undvika att dyra ingredienser med stor rabatt i kronor dominerar listan.

När procentläge är valt visas besparingar som procent även i receptkorten på startsidan och i popupen med erbjudandedetaljer.

### 5.3 Bostadsadress

Din hemadress, som används för att hitta närliggande butiker och leveransalternativ.

- Du kan skriva en adress för att få autoförslag (via OpenStreetMap)
- Eller fylla i fälten manuellt: gatuadress, postnummer (5 siffror) och ort
- Sparas automatiskt när du gör ändringar

**Observera:** Om du ändrar ditt postnummer kan dina e-handelsval behöva konfigureras om på Butikssidan, eftersom leveransområden beror på din plats.

### 5.4 Receptmatchningsinställningar

Här finjusterar du vilka recept som visas i dina förslag.

#### Antal ingredienser

Filtrera recept efter antal ingredienser. Använd reglagen för att ange en nedre och övre gräns (1–30). Markera **"Ingen gräns"** för att ta bort maxgränsen och visa alla recept oavsett hur många ingredienser de har.

Färre ingredienser = enklare recept. Nyttigt om du vill slippa komplicerade kvällsrätter, eller tvärtom vill filtrera bort för enkla recept.

#### Kategoriexkluderingar
Omkopplare för att helt dölja kategorier:
- **Exkludera kött** - Inga köttrecept alls
- **Exkludera fisk** - Inga fisk-/skaldjursrecept
- **Mejeriprodukter med laktos** - När aktiverat filtreras mejeriprodukter som innehåller laktos bort, men laktosfria alternativ (som Laktosfri mjölk) visas fortfarande.

#### Endast svenskt kött
När markerat filtreras importerat kött bort från erbjudandematchningen. Produkter med ursprung i andra länder (t.ex. "Brasilien", "Nya Zeeland") eller från kända importvarumärken döljs. Specialchark som alltid är importerad — som prosciutto, chorizo, salami och salsiccia — visas oavsett inställning.

#### Kategoribalans
Fyra rader med knappar (0-4) styr fördelningen av receptförslag mellan kategorier:

| Inställning | Effekt |
|-------------|--------|
| 0 | Kategorin dold helt |
| 1 | Minimalt - väldigt få recept från denna kategori |
| 2 | Under genomsnittet |
| 3 | Standard - balanserat |
| 4 | Maximum - prioritera denna kategori |

En visuell förhandsgranskning visar hur 12 receptplatser fördelas baserat på dina nuvarande inställningar. Klicka på **"Balansera"** för att återställa alla kategorier till standard (3-3-3-3).

#### Exkluderade varumärken
Ange varumärken du vill undvika (ett per rad eller kommaseparerat). Erbjudanden från dessa varumärken matchas inte mot recept.

#### Exkluderade ingredienser
Ange ingredienser du vill undvika. Recept som innehåller dessa ingredienser visas inte i förslag.

#### Filtrerade produkter
Ange produkttyper att exkludera från erbjudandematchning (t.ex. "juicekoncentrat", "snabbnudlar").

#### Visa omatchade erbjudanden
Klicka på denna knapp för att se en diagnostisk vy över varför vissa butikserbjudanden inte matchades mot något recept. Användbart för att förstå matchningssystemet. Visar filterorsaker som "icke-livsmedel", "varumärke exkluderat", "ingen receptmatchning", m.m.

#### Ingredienser som aldrig matchas

Vissa ingredienser är så vanliga i recept att de skulle skapa hundratals matchningar utan att ge användbart mervärde. Dessa **basvaror ignoreras medvetet** vid receptmatchning:

| Kategori | Ingredienser |
|----------|-------------|
| Bassmaksättning | salt, peppar, svartpeppar, vitpeppar, citronpeppar, vitlökspeppar |
| Matlagningsvätskor | vatten, olja |
| Sockertyper | socker (generiskt) |

**Vad innebär det i praktiken?** Om t.ex. "Svartpeppar Malen" är på extrapris kommer den inte att dyka upp som matchning i receptförslag — trots att många recept innehåller svartpeppar. Däremot matchas specifika kryddor (spiskummin, kanel, paprika m.fl.) som vanligt.

Utöver basvarorna ignoreras även:
- **Tillagningsmetoder** som produktbeskrivning (fryst, grillad, marinerad, rökt, m.fl.)
- **Förpackningsord** (burk, paket, flaska, m.fl.)
- **Märkesnamn** och marknadsföringsord (ekologisk, premium, klassisk, m.fl.)
- **Köksredskapsord** (glutenfri, laktosfri, vegansk — dietbeskrivningar, inte ingredienser)

### 5.5 Avancerade inställningar

#### Recepthantering

Hantera dubbletter, permanent exkluderade recept, omatchade produkter och stavningskontroll.

- **Hitta receptdubletter** — Söker igenom alla recept och hittar par med identiska ingredienslistor men olika namn eller URLer. En sida visar recepten sida vid sida med bild, namn, källa, URL och ingredienser.
  - **Dölj** — Döljer receptet (kan återställas via "Dolda recept"). Receptet ligger kvar i databasen men visas inte i sökresultat eller matchning.
  - **Ta bort permanent** — Raderar receptet ur databasen och lägger till URL:en i en exkluderingslista så att det inte hämtas igen vid nästa skrapning.

- **Exkluderade recept** — Visar alla permanent exkluderade recept med namn, källa och datum. Här kan du ta bort enskilda exkluderingar (så att receptet kan hämtas igen nästa gång skraparen körs) eller ta bort alla exkluderingar på en gång.

- **Visa omatchade varor** — Visar butikserbjudanden som inte matchat något recept, uppdelat efter orsak (filtrerad kategori, icke-livsmedel, bearbetad produkt, inga nyckelord, ingen receptmatchning). Användbart för att hitta luckor i matchningslogiken.

- **Stavningskontroll** — Visar alla automatiska stavningskorrigeringar som gjorts i receptingredienser. Korrigeringar sker automatiskt vid receptskrapning med Levenshtein-avstånd (max 1 tecken fel). Antalet aktiva korrigeringar visas i knappen.
  - Korrigeringar visas grupperade per ordpar (t.ex. "scharlottenlökar → schalottenlökar") med alla berörda recept listade under varje grupp. Varje recept har en länk till källan.
  - **Återställ** (gul knapp per recept) — Ångrar korrigeringen för just det receptet och förhindrar att den görs igen för det receptet.
  - **Korrigera aldrig detta ord** (röd knapp per grupp) — Ångrar korrigeringen i samtliga recept och förhindrar att ordparet korrigeras igen, oavsett recept.
  - **Visa blockerade** — Visar blockerade korrigeringar (både per-recept och globala). Härifrån kan man tillåta dem igen.
  - En siffra visas i Konfiguration-fliken i navbaren när det finns nya ogranskade korrigeringar.

#### Receptbilder

Hantera hur receptbilder lagras.

- **Spara bilder lokalt** - Cacha bilder på servern för snabbare laddning
- **Ladda ner automatiskt vid hämtning** - Ladda automatiskt ner bilder när nya recept hämtas

**Bildhanteringsknappar:**
- **Ladda ner saknade bilder** - Starta en bakgrundsnedladdning av alla saknade bilder. Visar realtidsförlopp med procent och tidsuppskattning. Kan avbrytas när som helst.
- **Rensa alla bilder** - Ta bort alla lokalt cachade bilder (de laddas istället från källwebbplatserna)

**Indikator för misslyckade bilder:**
- Grön bock: Alla bilder är OK
- Gul varning: Vissa bilder försöker igen (tillfälliga fel)
- Röd X: Vissa bilder misslyckades permanent efter 5 försök

Klicka på indikatorn för att hantera misslyckade bilder: försök igen individuellt, ta bort receptet, eller massradera alla misslyckade recept.

#### SSL/HTTPS

Hantera appens HTTPS-certifikat:

- **Statusmärke** visar om SSL är aktiverat, inaktiverat eller åsidosatt
- **Certifikatdetaljer** visar ämne, utgångsdatum och dagar kvar
- **Ladda upp** ett nytt certifikat och privat nyckel
- **Aktivera/Inaktivera** SSL (kräver omstart av containern)
- **Ta bort** befintliga certifikat

#### Reverse proxy (valfritt)

Appen fungerar direkt utan reverse proxy. Vill du lägga den bakom en (Nginx Proxy Manager, Traefik, Caddy m.fl.), behöver du konfigurera två saker i `.env`:

1. Lägg till proxyns hostname/domän i `ALLOWED_HOSTS` så att origin-validering godkänns
2. Sätt `TRUSTED_PROXY` till proxyns interna IP så att rate limiting ser klientens riktiga IP

```
ALLOWED_HOSTS=localhost,127.0.0.1,min-doman.example.com
TRUSTED_PROXY=172.18.0.1
```

Hitta proxyns IP med: `docker network inspect bridge | grep Gateway`

Starta sedan om web-containern med `docker compose up -d web` (restart laddar INTE om `.env`).

**Utan `TRUSTED_PROXY`:** Rate limiting använder proxyns IP för alla requests, dvs alla användare delar en gemensam rate limit. Det är säkert men mindre precist.

---

## 6. Tips & Vanliga frågor

### Bör jag schemalägga eller köra manuellt?

**Schemalägga är rekommenderat.** När erbjudanden eller recept hämtas byggs receptmatchningen om automatiskt. Med normalt antal erbjudanden tar det bara några sekunder, men själva hämtningen från butikens webbplats kan ta lite längre. Om du schemalägger hämtningarna (t.ex. på natten eller tidigt på morgonen) sker allt i bakgrunden och dina förslag är klara när du öppnar appen.

Du kan köra hämtningar manuellt också — men då får du vänta medan erbjudandena laddas ner och matchningen beräknas om.

### Hur ofta bör jag hämta erbjudanden?

Butikserbjudanden ändras vanligtvis varje vecka. Att ställa in ett **veckoschema** är idealiskt. Välj en dag då din butik brukar uppdatera sina erbjudanden (ofta måndag eller onsdag).

### Hur ofta bör jag hämta recept?

Receptkällor ändras inte lika ofta. Ett **månads-** eller **veckoschema** i inkrementell-läge räcker vanligtvis för att fånga nya recept.

### Varför visas inte vissa recept?

Det finns flera anledningar:

**Dina inställningar:**
- Kategoriexkluderingar kanske döljer dem
- Kategoribalansen kan vara satt till 0 för vissa kategorier
- Exkluderade varumärken, ingredienser eller produkter kanske filtrerar bort dem
- Receptet kan ha dolts manuellt (kolla "Visa dolda recept" i sökvyn)

**Säsongsfiltrering:**
Recept med tydliga säsongsord i namnet döljs automatiskt från startsidans förslag när de är utanför säsong. De kan dock alltid hittas via **Sök recept**. Säsongerna är:

| Högtid/Säsong | Nyckelord | Visas |
|---------------|-----------|-------|
| Jul | jul, pepparkak, glögg, lussebulle, advent | 1 dec – 6 jan |
| Nyår | nyår, nyårs | 27 dec – 2 jan |
| Semlor | semla, semlor, fettisdag | ~2 veckor kring fettisdagen |
| Påsk | påsk, påsklamm | 2 veckor före – 1 vecka efter påsk |
| Midsommar | midsommar | 1 vecka före midsommarafton |
| Kräftskiva | kräftskiva, surströmmingsskiva | hela augusti |
| Halloween | halloween | 24 okt – 3 nov |
| Sommarrecept | sommar... (sommargryta, sommarsallad) | jun – aug |
| Höstrecept | höst... (höstsoppa, höstgryta) | sep – nov |
| Vinterrecept | vinter... (vintervärmare) | dec – feb |

**Bufféer och festmenyer:**
Recept som är bufféer, trerättersmiddagar eller storkalas (30+ ingredienser) döljs från veckans förslag. De tenderar att dominera topplistorna på grund av sin storlek, men är sällan användbara för vardagsmiddag. Dessa kan fortfarande hittas via **Sök recept**.

### Varför matchar receptet "fel" produkter?

Matchningen är medvetet bred — målet är att visa vilka butikserbjudanden som är relevanta, inte att ge en perfekt inköpslista. Några saker att veta:

**Generella produktkategorier:** Vissa ingredienser matchas som grupp snarare än exakt:
- **Pasta** — "penne", "tagliatelle", "fusilli" och liknande matchar alla pastaprodukter. Anledning: de flesta recept fungerar med valfri pastatyp, och du vill se att pasta är på rea oavsett sort. Undantag: "spaghetti" matchar bara långpasta (inte t.ex. farfalle).
- **Ris** — "basmatiris" och "jasminris" matchar alla risprodukter, eftersom de flesta rätter fungerar med valfri ristyp. Undantag: "arborioris" matchar bara sig själv — det är specifikt för risotto och går inte att byta ut.
- **Ost** — "ost" matchar alla ostar. Receptet säger kanske "riven ost" men du vill se alla osttyper som är på extrapris. Specifika ostar som "västerbottensost" eller "mozzarella" matchar dock mer exakt.

**Brusmatchningar:** En ingrediens som "vitlök" kan matcha produkter som "Bruschetta Vitlök & Persilja" — det är en produkt som *innehåller* vitlök, inte vitlök i sig. Dessa visas för att ge en komplett bild, men du förväntas välja den produkt som passar.

**Smaknyanser:** Produkter med en ingrediens som smaksättning (t.ex. "Balsamvinäger Ingefära") kan dyka upp när receptet vill ha ren ingefära. Matchningen fångar att produkten har med ingrediensen att göra, men du väljer själv.

### Kan jag hitta säsongsrecept utanför säsong?

Ja. Använd **Sök recept** och sök på t.ex. "julskinka" eller "semlor" — de finns kvar i databasen och kan alltid hittas via sökning. Det är bara startsidans automatiska förslag som döljer dem utanför säsong.

### Kan jag använda Deal Meals på mobilen?

Ja! Gränssnittet är fullt responsivt och fungerar i mobilwebbläsare. Alla funktioner är tillgängliga på mindre skärmar.

### Vad gör stjärnan på en receptkälla?

Stjärnmärkta källor får en liten prioritering vid generering av förslag. Om du föredrar recept från en viss webbplats, stjärnmärk den källan.

### Hur sorteras recepten i varje kategori?

**Kött & Fågel, Fisk & Skaldjur och Vegetariskt** sorteras som standard efter total besparing i kronor — receptet med störst rabatt visas först. Om du under **Konfiguration > Sorteringsmetod** valt "Procent sparade" sorteras dessa istället efter genomsnittlig procentuell rabatt, viktat mot hur stor andel av ingredienserna som har erbjudanden.

**Smarta köp** använder en annan sortering. Istället för att bara titta på kronor premieras recept där du kan handla nästan allt på extrapris — inte bara ett par dyra ingredienser med stor rabatt, utan hela receptet med rimliga rabatter.

**Exempel:**

| Recept | Ingredienser på rea | Besparing | Visas som |
|--------|---------------------|-----------|-----------|
| A | 3 av 6 (50%) | 80 kr | Kött & Fågel (hög rabatt) |
| B | 5 av 7 (75%) | 40 kr | Smarta köp (bra täckning) |
| C | 6 av 7 (90%) | 30 kr | Smarta köp (bäst täckning) |

Recept C rankas högst i Smarta köp trots lägst besparing, eftersom nästan alla ingredienser finns på extrapris.

### Hur exakt är ingrediensmatchningen?

Matchningen är tänkt att vara praktiskt användbar, inte magisk. För svenska recept och svenska butikserbjudanden är målet ungefär **95-97% användbara matchningar** för receptingredienser som rimligen kan kopplas till en faktisk butiksvara.

100% träffsäkerhet går inte att uppnå i praktiken. Butiker byter namn på produkter, recept kan vara vaga, produktnamn innehåller varumärken och reklamtext, och vissa ingredienser går helt enkelt inte att koppla rent till veckans erbjudanden. Målet är "tillräckligt bra för att vara användbart", samtidigt som uppenbart felaktiga matchningar hålls nere.

Vissa förenklingar är medvetna. Till exempel klumpar systemet ihop pasta i breda familjer som pasta och långpasta, skiljer inte alltid på några vanliga rissorter, grupperar ofta ost ganska brett och är generellt inte superpetigt med vardagsvarianter av till exempel färskost eller senap.

Det gör att du själv kan välja exakt vilken variant du vill köpa, och det ökar chansen att ett faktiskt extrapris visas för ingrediensfamiljen istället för att ett användbart erbjudande döljs bara för att receptet och butiken råkar använda lite olika ord.

### Vad är skillnaden mellan e-handel och fysisk butik?

- **E-handel** visar erbjudanden vid nätbeställning (det du ser när du handlar på butikens webbplats för hemleverans)
- **Fysisk butik** visar erbjudanden i butiken (det du hittar i din lokala butik)

Erbjudandena kan skilja sig avsevärt mellan dessa två alternativ, även inom samma butikskedja.

### Mina förslag verkar inaktuella - vad gör jag?

1. Gå till **Butiker** och hämta erbjudanden på nytt för dina butiker
2. Gå tillbaka till **Startsidan** och klicka på **uppdateringsknappen** bredvid "Veckans fyndrecept"
3. Om det inte hjälper, hämta om relevanta receptkällor och vänta tills cacheuppbyggnaden är klar

### Hur byter jag språk?

Klicka på **flaggikonen** i navigeringsfältet högst upp och välj ditt föredragna språk. Sidan laddas om på det nya språket. Tillgängliga språk: Svenska och Engelska (Storbritannien).

### Hur växlar jag mellan ljust och mörkt läge?

Gå till **Konfiguration** och använd temareglaget högst upp på sidan. Ändringen tillämpas direkt på alla sidor.

### Kan jag lägga till egna recept?

Ja! Använd **Mina Recept**-källan för att lägga till recept från vilken webbplats som helst via URL. Klicka på kugghjulet på Mina Recept-kortet, klistra in en recept-URL och kör skraparen. Receptet måste ha en unik URL — du kan inte klistra in recepttext direkt. Se [Mina Recept](#45-mina-recept--lägg-till-egna-recept-via-url) för detaljer.

### Varför finns inte butik X eller receptsida Y?

Deal Meals är byggt med ett **modulärt pluginsystem** — varje butik och receptkälla är ett fristående plugin. De butiker och recept-webbsidor som finns med just nu är de som har implementerats hittills, men systemet är designat för att utökas.

Om du är bekväm med Python kan du skriva ditt eget plugin för att skrapa valfri butik eller receptsida. Varje plugin lever i sin egen mapp och följer en enkel mall. Se [HOW_TO_ADD_SCRAPERS.md](HOW_TO_ADD_SCRAPERS.md) för en steg-för-steg-guide om att lägga till nya butiker och receptkällor.

### Finns det inloggning eller lösenordsskydd?

Nej. Applikationen har ingen inbyggd autentisering — den är byggd för att köras på ett tryggt lokalt nätverk och bör inte exponeras direkt mot internet. Om du behöver åtkomst utifrån rekommenderas en reverse proxy med en identitetshanterare framför, t.ex. Nginx Proxy Manager, Traefik eller Caddy ihop med Authentik eller motsvarande.
