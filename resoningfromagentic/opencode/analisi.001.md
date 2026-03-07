Punti Deboli Identificati in TenderWriter

🔴 Critici

#	Problema	Localizzazione FIXATI OK
1	Secret/password hardcoded di default - app_secret_key, admin_password, JWT secret usano valori "changeme" di default	config.py:17,22,97
2	Documenti OnlyOffice in RAM - _document_store è un dict in-memory, si perde al riavvio del container	onlyoffice.py:194-198
3	Nessuna rate limiting - Endpoint registrazione/login senza protezione da brute force	auth.py

🟠 Alti
#	Problema	Localizzazione
4	OTP non verificato è consentito multiple retry - Nessun limite tentativi OTP, timing attack potenziale	auth.py:193-208
5	Password admin hardcoded nel codice - admin@admin.com / admin nel codice sorgente	config.py:21-22, main.py:57
6	Debug print in produzione - print() statement nel codice di produzione	auth.py:97,138,154,226
7	Logging espone dati sensibili - Email e OTP loggati in chiaro	auth.py:98

🟡 Medi

#	Problema	Localizzazione
8	Debug mode attivo di default - app_debug: bool = True	config.py:16
9	CORS configurato per localhost - Potrebbe essere troppo permissivo in produzione	config.py:18
10	Nessun cleanup documenti - _document_store cresce indefinitamente senza TTL	onlyoffice.py:196
11	Missing index su OTP - Query su OTPToken.token senza index	auth.py:201
12	Sessione JWT fissa 8h - Nessun refresh token mechanism	auth.py:35

🟢 Bassi

#	Problema
13	console.error left in frontend production code
14	Nulla esplicita validazione input lunghezza password
15	Nessun rate limiting sui richiami RAG
16	Solo 2 ruoli utente (admin/editor) - manca user manager