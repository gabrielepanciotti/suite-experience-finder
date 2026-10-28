# Guida d'uso di ExperienceFinder

## Cosa fa

ExperienceFinder è il finder di esperienze di viaggio del cluster Travel. I contenuti sono
schede Markdown nel vault `vault/wiki/`, divise tra `destinazioni/`, `esperienze/` e `radar/`.
Il backend offre API di sola lettura per destinazioni e guide; le guide pubblicate oggi
appartengono alla sezione `esperienze`. Il vault resta la fonte di verità: il database è una copia
derivata, aggiornata dall'importatore `experiencefinder_backend.vault_import` (le pagine `radar/`
non vengono importate). Il frontend di consultazione non c'è ancora: per ora si usano le API.

## Come si apre

- Frontend di sviluppo: <http://localhost:3354>
- API: <http://localhost:10020/api>; stato del servizio: <http://localhost:10020/api/health>
- Avvio con Docker: `docker compose --env-file .env -f deploy/docker-compose.example.yml up -d --build`

## Casi d'uso passo per passo

### Consultare le destinazioni via API

1. `GET /api/destinations` restituisce tutte le destinazioni, ordinate per titolo; non accetta
   parametri. Ogni risultato contiene `id`, `slug`, `title`, `paese`, `stagione_ideale`,
   `budget_medio`, `giorni_consigliati`, `coverage` e `tags`.
2. `GET /api/destinations/{id}` accetta come `{id}` sia l'ID numerico sia lo slug. Aggiunge
   `created`, `updated`, `sources`, `body` e `source_path`; se non trova la scheda risponde `404`.
3. `GET /api/guides` restituisce le guide ordinate per sezione e titolo. Il parametro query
   opzionale `section` accetta oggi solo `esperienze`, per esempio
   `GET /api/guides?section=esperienze`; altri valori producono `422`. I campi sono `id`, `slug`,
   `section`, `title`, `coverage`, `tags`, `created`, `updated`, `body` e `source_path`.

### Aggiungere o aggiornare una scheda nel vault

1. Crea o modifica una scheda Markdown nella relativa cartella di `vault/wiki/`.
2. Controlla frontmatter, titolo e contenuto della scheda.
3. Per renderla visibile nelle API riavvia il servizio backend oppure esegui l'importatore.

### Aggiornare i dati delle API dopo una modifica al vault

1. All'avvio il backend importa da solo `vault/wiki/destinazioni/*.md` nella tabella
   `destinations` e `vault/wiki/esperienze/*.md` nella tabella `guides` (sezione `esperienze`).
   In Docker il vault è montato in sola lettura, quindi basta riavviare il backend.
2. In alternativa lancia l'import a mano, senza riavvio:
   `docker exec experiencefinder-backend python -m experiencefinder_backend.vault_import`,
   oppure, fuori da Docker, dalla cartella `backend/`:
   `python -m experiencefinder_backend.vault_import [--vault DIR]`.
3. L'import è idempotente: aggiorna per slug, elimina le righe importate dal vault
   (`origin = "vault"`) la cui scheda non esiste più e non tocca le righe con altra origine.
   `visibility` si legge dal frontmatter (default `public`).
4. Una scheda con YAML non valido viene saltata e segnalata nei log; le altre vengono importate
   comunque. Il comando manuale esce con codice `1` se c'è stato almeno un errore.
5. Per disattivare l'import all'avvio imposta `VAULT_IMPORT_ON_STARTUP=0`; la cartella del vault
   si cambia con `VAULT_DIR` (default: `vault/` nella radice del nodo).

### Importare reel salvati da Instagram e aggiornare il radar

1. Installa le dipendenze locali: `yt-dlp`, `ffmpeg` e `faster-whisper` (la trascrizione usa la CPU).
2. Esporta i cookie Instagram in formato Netscape e avvia, per una raccolta privata:
   `python -m tools.reel_ingest --collection <URL_O_ID> --cookies <cookies.txt>`.
   In alternativa usa `--urls <URL> [<URL> ...]`. Sono disponibili anche `--audio-dir`,
   `--out-dir` e `--model`; i default sono `vault/raw/media`, `vault/raw/reels` e `small`.
3. Trasforma caption e trascrizione nei dati degli spot, quindi aggiorna il radar con:
   `python -m tools.radar_pool vault/wiki/radar/<regione>.md --regione <slug> --spots-json '<JSON>'`.
   Il JSON è una lista di oggetti con `name` e, facoltativamente, `kind`, `category`, `note`,
   `lat`, `lng`, `reel_url` e `source`; `--title` è opzionale.

### Creare il pool dei luoghi di un itinerario

1. Prepara l'HTML renderizzato di una lista Maps oppure una lista JSON di luoghi.
2. Esegui `python -m tools.places_pool <pool.md> --trip <slug> --from-html <lista.html> --source <URL>`;
   in alternativa sostituisci `--from-html` con `--places-json '<JSON>'`. `--title` è opzionale.
3. Lo strumento aggiunge solo i luoghi non già presenti per nome o coordinate.

## Servizi LLM

Il progetto non chiama modelli tramite API: la trascrizione usa `faster-whisper` in locale sulla CPU.

## Problemi comuni

- `/api/health` risponde `503` quando il database non è disponibile.
- `/api/destinations` e `/api/guides` rispondono vuote: controlla nei log del backend la riga
  «Startup vault import» e che il vault sia montato nel container (`../vault:/app/vault:ro` nel
  file Compose usato).
- Se la porta del database è occupata, cambia `DB_HOST_PORT` nel file `.env`.
- Senza cookie validi una raccolta Instagram privata non può essere letta.
- Se mancano `yt-dlp` o `ffmpeg`, `reel_ingest` segnala un warning e salta il reel interessato.
